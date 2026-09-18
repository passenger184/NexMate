"""Resolved-issue memory (Phase 4): confirmed edits become retrievable.

Every applied Tier-2 edit is already a git commit with a message and a
diff; the conversation that motivated it is the case study. This module
turns that bundle into ONE chunk in the SAME Chroma collection
(`source_type="resolved_issue"`), so "we saw this before — here's how it
was fixed" works through the ordinary retrieval/citation path
(docs/PHASE_4_SPEC.md). No separate memory store, no summarization.

Also provides --backfill for commits made before this existed: real Phase 2
edits get indexed with their true motivating context supplied at backfill
time (never invented).
"""

import argparse
import json
import subprocess
import uuid
from typing import Any

import chromadb

import config
from tools.pathsafe import PathOutsideRootError, resolve_in_project

RESOLUTION_MAX_CHARS = 2400  # diff portion is truncated past this


class BackfillError(Exception):
    pass


def _git(*args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=config.PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BackfillError(f"git could not run: {exc}") from exc
    if proc.returncode != 0:
        raise BackfillError(
            f"git {' '.join(args[:2])} failed: {proc.stderr.strip()}"
        )
    return proc.stdout


def read_commit(commit_hash: str) -> dict[str, str]:
    """{hash, message, files, diff} for one commit (for backfills)."""
    short = _git("rev-parse", "--short", commit_hash).strip()
    if not short:
        raise BackfillError(f"{commit_hash!r} did not resolve to a commit")
    message = _git("log", "-1", "--format=%s", short).strip()
    files = [
        line for line in _git(
            "show", "--name-only", "--format=", short
        ).splitlines() if line.strip()
    ]
    diff = _git("show", "-p", "--format=", short)
    return {"hash": short, "message": message,
            "files": files, "diff": diff}


def build_resolution_document(
    rel_path: str,
    commit_hash: str,
    message: str,
    context: str,
    diff: str,
    site: str = "",
) -> tuple[str, dict[str, Any]]:
    """One retrievable chunk describing a resolved issue.

    Text order encodes value: what was asked -> what was done ->
    evidence. url_or_path embeds the commit hash so per-document dedupe
    never collapses two resolutions against the same file.
    """
    context_block = context.strip() or "(no conversational context recorded)"
    diff_budget = max(
        200, config.RESPLIT_THRESHOLD_CHARS - len(context_block) - len(message)
    )
    diff_text = diff if len(diff) <= diff_budget else (
        diff[:diff_budget] + "\n… [diff truncated]"
    )
    text = (
        f"Resolved issue in {rel_path} (commit {commit_hash}).\n"
        f"Why it came up: {context_block}\n"
        f"What was changed: {message}\n"
        f"Diff:\n{diff_text}"
    )
    metadata = {
        "title": f"resolved_issue: {rel_path}",
        "section": f"commit {commit_hash}",
        "url_or_path": f"{rel_path}@{commit_hash}",
        "source_type": "resolved_issue",
        "updated": "",
    }
    from rag import acl
    acl.stamp_metadata(metadata, "resolved_issue", site)
    return text, metadata


def index_resolution(
    rel_path: str,
    commit_hash: str,
    message: str,
    context: str = "",
    diff: str = "",
    site: str | None = None,
) -> dict[str, Any]:
    """Embed + insert one resolution chunk into the shared collection."""
    # Path safety even here: resolutions reference project-relative paths.
    try:
        resolve_in_project(rel_path)
    except PathOutsideRootError as exc:
        raise BackfillError(f"refusing out-of-root resolution: {exc}") from exc

    from rag.retriever import get_chroma_collection, _get_embed_model

    if site is None:
        import os
        site = os.environ.get("NEXMATE_FRAPPE_SITE", "")
    text, metadata = build_resolution_document(
        rel_path, commit_hash, message, context, diff, site
    )
    embedding = _get_embed_model().get_text_embedding(text)
    collection = get_chroma_collection()
    doc_id = uuid.uuid4().hex
    collection.add(
        ids=[doc_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata],
    )
    return {"indexed": True, "chunk_id": doc_id, "url_or_path":
            metadata["url_or_path"]}


def backfill_commit(commit_hash: str, context: str) -> dict[str, Any]:
    """Index an existing Phase 2 edit commit as a resolved issue."""
    info = read_commit(commit_hash)
    if len(info["files"]) != 1:
        raise BackfillError(
            f"commit {info['hash']} touches {len(info['files'])} files; "
            "backfill expects the single-file atomic commits this tool "
            "produces"
        )
    return index_resolution(
        rel_path=info["files"][0],
        commit_hash=info["hash"],
        message=info["message"],
        context=context,
        diff=info["diff"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backfill-commit", required=True)
    parser.add_argument("--context", required=True,
                        help="the real motivation behind this commit")
    args = parser.parse_args()
    result = backfill_commit(args.backfill_commit, args.context)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
