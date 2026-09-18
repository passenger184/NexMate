"""Ingest THIS project's own source + internal docs into the Chroma store.

Phase 3 "Company Knowledge" (docs/PHASE_3_SPEC.md): the same single
collection that holds public framework docs gains two tagged corpora —

  source_type="our_code"     .py files under rag/, tools/, service/,
                             ingestion/, evaluation/, tests/, frappe_app/
  source_type="company_doc"  this repo's own markdown (README, PROJECT,
                             ARCHITECTURE, docs/*.md, progress/*.md, ...)

so retrieval can cite "your tools/edit.py" instead of generic framework
pages, per ARCHITECTURE.md's knowledge-layering note.

Chunking: function/class boundaries via the stdlib `ast` module for Python
(PHASE_3_SPEC explicitly prefers simple boundary chunking over tree-sitter
until proven inadequate); MarkdownNodeParser headings for markdown; both
re-split with the same SentenceSplitter budget as the public pipeline.
Non-Python/non-markdown files are skipped — the JS bundle and JSON configs
carry little retrievable narrative value (logged assumption).

Idempotent: existing our_code/company_doc chunks are deleted before insert,
so re-runs after code changes stay consistent. Public-doc chunks are never
touched.

Usage:
    python -m ingestion.ingest_project            # sync this repo -> index
    python -m ingestion.ingest_project --dry-run  # report only
"""

import argparse
import ast
import sys
from pathlib import Path
from typing import Any

import chromadb
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

import config
from rag import acl

SOURCE_TYPES = ("our_code", "company_doc")

# Directories that are runtime artifacts, not knowledge.
SKIP_DIRS = {
    ".git", ".venv", ".venv-eval", "__pycache__", "node_modules",
    "data", ".ruff_cache", ".mypy_cache",
}
CODE_EXTENSIONS = {".py"}
DOC_EXTENSIONS = {".md"}


def _iter_project_files() -> list[Path]:
    """First-party .py/.md files, stable order, artifacts excluded."""
    root = config.PROJECT_ROOT
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix in CODE_EXTENSIONS or path.suffix in DOC_EXTENSIONS:
            files.append(path)
    return files


def _split_oversized(text: str, splitter: SentenceSplitter) -> list[str]:
    if len(text) <= config.RESPLIT_THRESHOLD_CHARS:
        return [text]
    return [p.get_content() for p in splitter.get_nodes_from_documents(
        [Document(text=text)])]


def split_python(text: str) -> list[tuple[str, str]]:
    """Function/class-boundary chunks as (symbol_path, code_text).

    Module preamble (docstring/imports/module-level constants) becomes its
    own chunk when substantial. Classes larger than the resplit budget are
    subdivided at method boundaries with a ClassName.method symbol path so
    one huge class doesn't become an unusable mega-chunk.
    """
    lines = text.splitlines(keepends=True)
    splitter = SentenceSplitter(
        chunk_size=config.CHUNK_SIZE_TOKENS,
        chunk_overlap=config.CHUNK_OVERLAP_TOKENS,
    )
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [("(module)", text)]

    segments: list[tuple[str, str]] = []
    preamble_end = 0

    def emit(symbol: str, start_line: int, end_line: int) -> None:
        body = "".join(lines[start_line - 1:end_line]).strip("\n")
        if len(body.strip()) < config.MIN_CHUNK_CHARS:
            return
        for piece in _split_oversized(body, splitter):
            segments.append((symbol, piece))

    top_nodes = list(tree.body)
    for node in top_nodes:
        end = getattr(node, "end_lineno", None)
        if end is None:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            emit(node.name, node.lineno, end)
            preamble_end = max(preamble_end, end)
        elif isinstance(node, ast.ClassDef):
            methods = [
                m for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                and getattr(m, "end_lineno", None)
            ]
            class_len = sum(len("".join(lines[m.lineno - 1:m.end_lineno]))
                            for m in methods)
            if (class_len > config.RESPLIT_THRESHOLD_CHARS
                    and len(methods) > 1):
                header = "".join(lines[node.lineno - 1:methods[0].lineno - 1])
                for m in methods:
                    emit(f"{node.name}.{m.name}", m.lineno, m.end_lineno)
                if header.strip():
                    segments.append((node.name, header.strip("\n")))
            else:
                emit(node.name, node.lineno, end)
            preamble_end = max(preamble_end, end)

    preamble = "".join(lines[:preamble_end]).strip("\n") if preamble_end else ""
    # Anything not covered by a top-level def/class (imports, constants,
    # module docstring, trailing main blocks).
    covered = set()
    for node in top_nodes:
        end = getattr(node, "end_lineno", None)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and end:
            covered.update(range(node.lineno, end + 1))
    rest_lines = [ln for i, ln in enumerate(lines, start=1) if i not in covered]
    rest = "".join(rest_lines).strip("\n")
    if len(rest.strip()) >= config.MIN_CHUNK_CHARS:
        for piece in _split_oversized(rest, splitter):
            segments.insert(0, ("(module)", piece))
    elif not segments and preamble:
        segments.append(("(module)", preamble))

    # A standalone docstring-only chunk competes badly in per-document
    # dedupe (found 2026-08-24: it beat resolve_in_project itself, so P1
    # got the module intro without the mechanism and generation declined).
    # Merge the preamble into the first real segment instead.
    if len(segments) > 1 and segments[0][0] == "(module)":
        preamble_chunk = segments.pop(0)
        sym, body = segments[0]
        segments[0] = (
            sym,
            f"{preamble_chunk[1]}\n\n{body}",
        )
        if len(segments[0][1]) > config.RESPLIT_THRESHOLD_CHARS:
            pieces = _split_oversized(segments[0][1], splitter)
            segments[0:1] = [(sym, p) for p in pieces]
    if not segments:
        segments.append(("(module)", text))
    return segments


def _load_markdown(path: Path, site: str) -> list[Document]:
    raw = path.read_text(encoding="utf-8")
    rel = path.relative_to(config.PROJECT_ROOT).as_posix()
    base_meta = acl.stamp_metadata({
        "title": rel,
        "url_or_path": rel,
        "source_type": "company_doc",
        "updated": "",
    }, "company_doc", site)
    nodes = MarkdownNodeParser().get_nodes_from_documents(
        [Document(text=raw, metadata=dict(base_meta))]
    )
    out: list[Document] = []
    splitter = SentenceSplitter(
        chunk_size=config.CHUNK_SIZE_TOKENS,
        chunk_overlap=config.CHUNK_OVERLAP_TOKENS,
    )
    for node in nodes:
        section = node.metadata.pop("header_path", "") or "(top)"
        node.metadata["section"] = section
        node.metadata["title"] = rel
        node.metadata["source_type"] = "company_doc"
        node.metadata["url_or_path"] = rel
        node.metadata["updated"] = ""
        for piece in _split_oversized(node.get_content(), splitter):
            meta = dict(node.metadata)
            out.append(Document(text=piece, metadata=meta))
    return [d for d in out
            if len(d.get_content().strip()) >= config.MIN_CHUNK_CHARS]


def load_project_documents(dry_run: bool = False, site: str = ""
                            ) -> tuple[list[Document], dict[str, int]]:
    """Build Documents from this repo; returns (docs, per-type counts)."""
    docs: list[Document] = []
    counts = {"our_code": 0, "company_doc": 0}
    for path in _iter_project_files():
        rel = path.relative_to(config.PROJECT_ROOT).as_posix()
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"  skipping non-UTF-8 file {rel}", file=sys.stderr)
            continue

        if path.suffix == ".py":
            chunks: list[tuple[str, str]] = split_python(raw)
            new = [
                Document(
                    text=piece,
                    metadata=acl.stamp_metadata({
                        "title": rel,
                        "section": symbol,
                        "url_or_path": rel,
                        "source_type": "our_code",
                        "updated": "",
                    }, "our_code", site),
                )
                for symbol, piece in chunks
            ]
        elif path.suffix == ".md":
            new = _load_markdown(path, site)
        else:
            continue
        docs.extend(new)
        counts["our_code" if path.suffix == ".py" else "company_doc"] += len(new)

    # Chroma silently skips empty-text nodes ("missing content") — that
    # would desync our bookkeeping from reality, so drop them HERE, loudly.
    non_empty = [d for d in docs if d.get_content().strip()]
    dropped = len(docs) - len(non_empty)
    if dropped:
        print(f"Dropped {dropped} empty-content chunks before insert "
              "(fail-loud replacement for Chroma's silent skip)")
    print(f"Project corpus: {len(non_empty)} chunks "
          f"(our_code={counts['our_code']}, company_doc={counts['company_doc']}) "
          f"from {len(_iter_project_files())} files")
    if dry_run:
        sample = next((d for d in non_empty
                       if d.metadata["source_type"] == "our_code"), None)
        if sample:
            print("Sample code chunk:", sample.metadata,
                  "::", sample.get_content()[:120].replace("\n", " | "))
    return non_empty, counts


def sync_to_chroma(docs: list[Document], site: str = "",
                   collection_name: str | None = None) -> int:
    """Delete stale project chunks, then embed+insert the fresh corpus.

    Targets the live collection by default; scoped rebuilds pass the staged
    collection name (which was seeded from the parent generation first).
    """
    for doc in docs:
        acl.stamp_metadata(doc.metadata, doc.metadata.get("source_type", ""), site)
    acl.assert_stamped(docs)
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    target = collection_name or config.COLLECTION_NAME
    collection = client.get_collection(target)
    before_public = collection.count()
    existing = collection.get(where={"source_type": {"$in": list(SOURCE_TYPES)}})
    stale_ids = existing["ids"]
    if stale_ids:
        collection.delete(ids=stale_ids)
    print(f"Removed {len(stale_ids)} stale project chunks "
          f"(public count preserved: {before_public - len(stale_ids)})")

    embed_model = HuggingFaceEmbedding(model_name=config.EMBEDDING_MODEL_NAME)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    VectorStoreIndex(
        docs,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=True,
    )
    total = collection.count()
    print(f"Index now holds {total} chunks "
          f"(public {total - len(docs)}, project {len(docs)})")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be ingested; write nothing")
    parser.add_argument("--site", default=None,
                        help="Frappe site owning company chunks "
                             "(defaults to $NEXMATE_FRAPPE_SITE; required "
                             "unless --dry-run, else stamped unreachable)")
    parser.add_argument("--collection", default=None,
                        help="staged collection name for scoped rebuilds "
                             "(default: live collection)")
    args = parser.parse_args()

    import os
    site = args.site or os.environ.get("NEXMATE_FRAPPE_SITE", "")
    docs, _ = load_project_documents(dry_run=args.dry_run, site=site)
    if not docs:
        raise SystemExit("No project documents found — nothing to ingest")
    if not args.dry_run:
        if not site:
            raise SystemExit(
                "Refusing company ingestion without a site: pass --site or "
                "set NEXMATE_FRAPPE_SITE (unstamped company chunks would be "
                "unreachable by every scope).")
        sync_to_chroma(docs, site, collection_name=args.collection)


if __name__ == "__main__":
    main()
