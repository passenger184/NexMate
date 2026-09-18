"""Chunk crawled doc markdown and embed it into the persistent Chroma store.

Two-stage chunking per DECISIONS.md [2026-08-23]:
  1. MarkdownNodeParser splits each page at markdown headings (H1-H6),
     code-fence aware, propagating a `header_path` per section.
  2. Sections larger than RESPLIT_THRESHOLD_CHARS are re-split with
     SentenceSplitter (~CHUNK_SIZE_TOKENS tokens, CHUNK_OVERLAP_TOKENS
     overlap) so no chunk blows past the embedding model's practical window.

Every node carries scalar metadata (Chroma requirement):
title, section, url_or_path, source_type="public_doc", updated.

Usage:
    python -m ingestion.chunk_and_embed            # full rebuild
    python -m ingestion.chunk_and_embed --limit 20 # smoke test
"""

import argparse
import re
import sys
from pathlib import Path

import chromadb
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

import config
from rag import acl

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
# Some wiki pages embed screenshots as multi-KB inline base64 data-URIs.
# Left in, they become unsplittable gibberish chunks whose embeddings all
# cluster together and flood top-k for unrelated queries (found via the
# Sales Return FAQ dominating results on 2026-08-23).
BASE64_DATA_URI_RE = re.compile(r"!?\[[^\]]*\]\(data:[^)]*\)")


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Return ({front_matter_key: value}, body_without_front_matter).

    Minimal parser for the wiki's flat `key: value` front-matter — avoids
    assuming a YAML dependency for three string fields.
    """
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            # wiki front-matter quirks: quoted values ("Title"), literal
            # backslash-n / backslash-t escape sequences in some titles
            fields[key.strip()] = (
                value.strip().strip("'\"")
                .replace("\\n", " ").replace("\\t", " ").strip()
            )
    return fields, text[match.end():]


def _load_documents(limit: int | None = None) -> list[Document]:
    """Load cached markdown pages as LlamaIndex Documents with metadata."""
    files = sorted(config.RAW_DOCS_DIR.rglob("*.md"))
    if limit is not None:
        files = files[:limit]
    if not files:
        raise SystemExit(
            f"No markdown found under {config.RAW_DOCS_DIR}. "
            "Run `python -m ingestion.scrape_or_load_docs` first."
        )

    docs: list[Document] = []
    skipped = 0
    seen_urls: set[str] = set()
    for path in files:
        rel_path = path.relative_to(config.RAW_DOCS_DIR).with_suffix("")
        rel_posix = f"/{rel_path.as_posix()}"
        # Re-apply the crawler's scope rules here (not only at crawl time):
        # stale cache entries from before a filter existed would otherwise
        # still be embedded (found 2026-08-24: one /erpnext/v13/ page leaked
        # into the v4 index and surfaced in answers' source lists).
        if config.is_excluded_doc_path(rel_posix):
            skipped += 1
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"  skipping unreadable file {path}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        fields, body = _split_front_matter(raw)
        # Deterministic canonical URL from the cached path structure,
        # independent of whether the page's own front-matter is well-formed.
        url = f"https://docs.frappe.io/{rel_path.as_posix()}"
        canonical = str(fields.get("url") or url)
        if canonical in seen_urls:
            # The wiki serves {alias}.md directly for many stale aliases,
            # so identical pages can be cached under several paths; index
            # each canonical page once (dedupe verified 2026-08-23:
            # 1,606 cached files -> 1,000 distinct pages).
            skipped += 1
            continue
        seen_urls.add(canonical)
        title = fields.get("title") or rel_path.as_posix()
        metadata = {
            "title": str(title),
            "section": "",  # filled per-node from header_path after parsing
            "url_or_path": canonical,
            "source_type": config.SOURCE_TYPE_PUBLIC_DOC,
            "updated": str(fields.get("updated", "")),
        }
        acl.stamp_metadata(metadata, config.SOURCE_TYPE_PUBLIC_DOC)
        if body.strip():
            body = BASE64_DATA_URI_RE.sub("[image]", body)
            docs.append(Document(text=body, metadata=metadata))
    print(f"Loaded {len(docs)} documents "
          f"({skipped} unreadable/duplicate skipped) from {config.RAW_DOCS_DIR}")
    return docs


def _chunk(docs: list[Document]) -> list:
    """Heading-based parse, then token-cap re-split of oversized sections."""
    md_nodes = MarkdownNodeParser().get_nodes_from_documents(docs)
    for node in md_nodes:
        header_path = node.metadata.pop("header_path", "")
        node.metadata["section"] = header_path or "(top)"

    splitter = SentenceSplitter(
        chunk_size=config.CHUNK_SIZE_TOKENS,
        chunk_overlap=config.CHUNK_OVERLAP_TOKENS,
    )
    nodes: list = []
    resplit_count = 0
    for node in md_nodes:
        if len(node.get_content()) > config.RESPLIT_THRESHOLD_CHARS:
            pieces = splitter.get_nodes_from_documents([node])
            resplit_count += 1
            nodes.extend(pieces)
        else:
            nodes.append(node)

    # Drop junk stubs (heading fragments, stray "---", single words):
    # they carry no retrievable meaning but can surface as citations.
    before = len(nodes)
    nodes = [n for n in nodes if len(n.get_content().strip()) >= config.MIN_CHUNK_CHARS]
    print(f"Dropped {before - len(nodes)} sub-{config.MIN_CHUNK_CHARS}-char stub chunks")

    sizes = sorted(len(n.get_content()) for n in nodes)
    print(f"Chunked: {len(md_nodes)} heading-sections -> {len(nodes)} chunks "
          f"({resplit_count} oversized sections re-split)")
    print(f"Chunk chars: min={sizes[0]} median={sizes[len(sizes)//2]} "
          f"max={sizes[-1]}")
    return nodes


def _embed_and_store(nodes: list, collection_name: str | None = None) -> None:
    """Embed all chunks into a cosine-space Chroma collection.

    Default target is the live collection (destructive rebuild — kept for
    the initial bootstrap only). Scoped rebuilds pass a staged collection
    name instead; publication happens through generations.publish_generation,
    never by deleting live state here.
    """
    embed_model = HuggingFaceEmbedding(model_name=config.EMBEDDING_MODEL_NAME)

    target = collection_name or config.COLLECTION_NAME
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    existing = [c.name for c in client.list_collections()]
    if not collection_name and target in existing:
        client.delete_collection(target)
        print(f"Dropped existing collection '{target}'")
    # hnsw:space MUST be cosine so exp(-distance) similarity thresholds in
    # config.py mean what they claim (chroma default is l2).
    collection = client.get_or_create_collection(
        target, metadata={"hnsw:space": "cosine"}
    )
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    index = VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=True,
    )
    count = collection.count()
    if count != len(nodes):
        raise SystemExit(f"Store mismatch: {len(nodes)} chunks built, "
                         f"{count} landed in Chroma")
    print(f"Embedded {count} chunks into {config.CHROMA_DIR} "
          f"(collection '{target}', cosine space)")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None,
                        help="only ingest the first N cached pages (smoke test)")
    parser.add_argument("--collection", default=None,
                        help="staged collection name for scoped rebuilds "
                             "(default: live collection, destructive)")
    args = parser.parse_args()

    documents = _load_documents(limit=args.limit)
    nodes = _chunk(documents)
    acl.assert_stamped(nodes)

    sample = nodes[0]
    print("\nSample chunk for verification:")
    print(f"  metadata: {sample.metadata}")
    print(f"  content[:300]: {sample.get_content()[:300]!r}")

    _embed_and_store(nodes, collection_name=args.collection)


if __name__ == "__main__":
    main()
