"""Versioned index generations (M4 index-lifecycle).

Every published index state is an explicit generation: vectors plus the
lexical snapshot built from one staged snapshot, activated by an atomic
pointer swap, with the prior generation retained for rollback. Deletions
and updates land only via new generations; destructive full-collection
replacement is prohibited.

Manifest layout under config.GENERATIONS_DIR:
  <gen-id>/manifest.json   - id, created, parent, sources, fingerprint,
                             acl_schema_version, per-corpus counts
  active.json              - {"active": <gen-id>} (atomic replace on swap)

The legacy pre-generation store is generation "gen-0-legacy": served as-is
until the first controlled rebuild, never silently migrated.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import config

LEGACY_GENERATION_ID = "gen-0-legacy"
REQUIRED_FINGERPRINT_FIELDS = ("model", "revision", "dimensions", "metric")


def _generations_dir() -> Path:
    config.GENERATIONS_DIR.mkdir(parents=True, exist_ok=True)
    return config.GENERATIONS_DIR


def embedding_fingerprint(model_name: str, dimensions: int,
                          revision: str = "unknown",
                          metric: str = "cosine") -> dict[str, Any]:
    """Fingerprint record for an embedding configuration."""
    return {"model": model_name, "revision": revision,
            "dimensions": int(dimensions), "metric": metric}


def fingerprint_compatible(stored: dict, current: dict) -> bool:
    """Strict on model/dimensions/metric; revision enforced when known.

    A stored "unknown" revision never blocks (legacy data), but a known
    revision mismatch refuses: silent incompatibility corrupts ranking
    without errors, so the check fails loud instead.
    """
    for field in ("model", "dimensions", "metric"):
        if stored.get(field) != current.get(field):
            return False
    stored_rev, current_rev = stored.get("revision"), current.get("revision")
    if (stored_rev not in (None, "unknown")
            and current_rev not in (None, "unknown")
            and stored_rev != current_rev):
        return False
    return True


def new_generation_id() -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rand = hashlib.sha256(f"{time.time_ns()}".encode()).hexdigest()[:8]
    return f"gen-{stamp}-{rand}"


def manifest_path(gen_id: str) -> Path:
    return _generations_dir() / gen_id / "manifest.json"


def write_manifest(gen_id: str, *, parent: str | None,
                   sources: dict[str, str],
                   fingerprint: dict[str, Any],
                   acl_schema_version: int,
                   counts: dict[str, int]) -> dict[str, Any]:
    """Persist a staged generation manifest; returns it."""
    for field in REQUIRED_FINGERPRINT_FIELDS:
        if field not in fingerprint:
            raise ValueError(f"fingerprint missing {field!r}")
    manifest = {
        "id": gen_id,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parent": parent,
        "sources": dict(sources),
        "embedding_fingerprint": dict(fingerprint),
        "acl_schema_version": int(acl_schema_version),
        "counts": dict(counts),
    }
    path = manifest_path(gen_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp.replace(path)
    return manifest


def read_manifest(gen_id: str) -> dict[str, Any]:
    path = manifest_path(gen_id)
    if not path.exists():
        raise RuntimeError(f"Unknown index generation {gen_id!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def active_generation_id() -> str | None:
    """Active generation, or None when serving the legacy store."""
    pointer = _generations_dir() / config.GENERATION_ACTIVE_POINTER
    if not pointer.exists():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Unreadable generation pointer: {exc}") from exc
    gen_id = data.get("active")
    if not gen_id:
        raise RuntimeError("Generation pointer has no active generation")
    return gen_id


def publish_generation(gen_id: str, verify) -> dict[str, Any]:
    """Activate a staged generation after verification; fail loud otherwise.

    `verify` is a zero-arg callable returning True when counts, fingerprint,
    and probe queries pass. The pointer swap is atomic (temp-file replace);
    a failed verification never touches the active pointer.
    """
    manifest = read_manifest(gen_id)
    if is_revoked(gen_id):
        raise RuntimeError(
            f"Generation {gen_id!r} is retired by an ACL revocation; "
            f"republication refused")
    if not verify():
        raise RuntimeError(
            f"Generation {gen_id!r} failed publication verification")
    pointer = _generations_dir() / config.GENERATION_ACTIVE_POINTER
    tmp = pointer.with_suffix(".tmp")
    tmp.write_text(json.dumps({"active": gen_id}), encoding="utf-8")
    tmp.replace(pointer)
    return manifest


def rollback_generation() -> dict[str, Any]:
    """Reactivate the parent of the active generation (one step back).

    Refuses targets retired by an ACL revocation: a superseded generation
    MUST NOT serve affected scope again while the revocation stands.
    """
    active = active_generation_id()
    if active is None:
        raise RuntimeError("No published generation to roll back from")
    parent = read_manifest(active).get("parent") or LEGACY_GENERATION_ID
    if parent != LEGACY_GENERATION_ID and is_revoked(parent):
        raise RuntimeError(
            f"Generation {parent!r} is retired by an ACL revocation; "
            f"rollback refused")
    pointer = _generations_dir() / config.GENERATION_ACTIVE_POINTER
    tmp = pointer.with_suffix(".tmp")
    tmp.write_text(json.dumps({"active": parent}), encoding="utf-8")
    tmp.replace(pointer)
    if parent == LEGACY_GENERATION_ID:
        return {"id": parent, "legacy": True}
    return read_manifest(parent)


def _revocations_path() -> Path:
    return _generations_dir() / "revocations.json"


def revoke_generation(gen_id: str, reason: str = "acl") -> dict[str, Any]:
    """Retire a generation after an ACL revocation (fail-closed ledger).

    A retired generation MUST NOT be reactivated while the revocation
    stands; already-delivered answers are historical. Revocation completes
    when the remediating generation publishes AND the superseded one is
    retired here.
    """
    if gen_id == LEGACY_GENERATION_ID:
        raise ValueError("The legacy store has no manifest to retire; "
                         "re-index instead")
    read_manifest(gen_id)  # fail loud on unknown generations
    path = _revocations_path()
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        record = {}
    record[gen_id] = {"reason": reason,
                      "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                              time.gmtime())}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {"id": gen_id, "revoked": True, "reason": reason}


def is_revoked(gen_id: str) -> bool:
    """Whether a generation is retired by an unlifted revocation."""
    try:
        record = json.loads(_revocations_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return gen_id in record


def collection_name_for(generation: str | None) -> str:
    """Physical collection backing a generation (legacy = historic store)."""
    if generation in (None, LEGACY_GENERATION_ID):
        return config.COLLECTION_NAME
    return f"{config.COLLECTION_NAME}--{generation}"


def _client():
    import chromadb
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR))


def count_by_source(collection) -> dict[str, int]:
    """Per-source_type chunk counts (publication verification input)."""
    counts: dict[str, int] = {}
    data = collection.get(include=["metadatas"])
    for meta in data.get("metadatas") or []:
        key = str((meta or {}).get("source_type", ""))
        counts[key] = counts.get(key, 0) + 1
    return counts


def seed_staged_from(staged_name: str, parent: str | None,
                     drop_source_types: tuple = ()) -> int:
    """Copy a parent generation into a fresh staged collection.

    Used for corpus-scoped rebuilds: seed everything, drop the corpus being
    rebuilt, then run that corpus's pipeline into the staged collection.
    Vectors are copied with their embeddings (no re-embed); unrelated
    corpora are preserved bit-for-bit. Returns chunks copied.
    """
    client = _client()
    try:
        client.delete_collection(staged_name)
    except Exception:
        pass
    src = client.get_collection(collection_name_for(parent))
    dst = client.get_or_create_collection(
        staged_name, metadata={"hnsw:space": "cosine"})
    data = src.get(include=["documents", "embeddings", "metadatas"])
    ids = data.get("ids") or []
    keep = [i for i, m in enumerate(data.get("metadatas") or [])
            if (m or {}).get("source_type") not in drop_source_types]
    for start in range(0, len(keep), 2000):
        batch = keep[start:start + 2000]
        dst.add(
            ids=[ids[i] for i in batch],
            embeddings=[data["embeddings"][i] for i in batch],
            documents=[data["documents"][i] for i in batch],
            metadatas=[data["metadatas"][i] for i in batch],
        )
    return len(keep)


def backfill_acl_metadata(collection_name: str, site: str,
                          backup_path: str | None = None) -> dict[str, int]:
    """Stamp ACL metadata onto a legacy collection in place (migration).

    Vectors are untouched (no re-embed): only metadata is merged. Public
    chunks become global; company tiers take `site`. Optionally writes a
    JSONL backup of prior metadatas for rollback. Returns per-visibility
    counts. Refuses an empty site (company chunks would stamp unreachable).
    """
    from rag import acl

    if not site:
        raise ValueError("backfill requires an explicit site")
    client = _client()
    collection = client.get_collection(collection_name)
    data = collection.get(include=["metadatas"])
    ids = data.get("ids") or []
    metas = data.get("metadatas") or []
    if backup_path:
        with open(backup_path, "w", encoding="utf-8") as fh:
            for cid, meta in zip(ids, metas):
                fh.write(json.dumps({"id": cid, "metadata": meta or {}}) + "\n")
    counts: dict[str, int] = {}
    for start in range(0, len(ids), 2000):
        batch_ids, batch_metas = [], []
        for cid, meta in zip(ids[start:start + 2000], metas[start:start + 2000]):
            merged = dict(meta or {})
            acl.stamp_metadata(
                merged, merged.get("source_type", ""), site)
            batch_ids.append(cid)
            batch_metas.append(merged)
            vis = merged["visibility"]
            counts[vis] = counts.get(vis, 0) + 1
        collection.update(ids=batch_ids, metadatas=batch_metas)
    return counts


def verify_generation(gen_id: str, current_fingerprint: dict) -> bool:
    """Publication gate: fingerprint, counts, and non-emptiness.

    Compares the staged collection against its own manifest (per-corpus
    counts must match exactly) and the manifest fingerprint against the
    live embedding setup. Returns True only when everything checks out;
    raises RuntimeError describing the first failure (fail loud).
    """
    manifest = read_manifest(gen_id)
    stored = manifest.get("embedding_fingerprint", {})
    if not fingerprint_compatible(stored, current_fingerprint):
        raise RuntimeError(
            f"Generation {gen_id!r}: embedding fingerprint mismatch "
            f"(stored {stored} vs current {current_fingerprint})")
    if manifest.get("acl_schema_version") != config.ACL_SCHEMA_VERSION:
        raise RuntimeError(
            f"Generation {gen_id!r}: unsupported ACL schema version "
            f"{manifest.get('acl_schema_version')!r}")
    staged_name = collection_name_for(gen_id)
    try:
        staged = _client().get_collection(staged_name)
    except Exception as exc:
        raise RuntimeError(
            f"Generation {gen_id!r}: staged collection "
            f"{staged_name!r} missing") from exc
    actual = count_by_source(staged)
    expected = manifest.get("counts", {})
    if actual != expected:
        raise RuntimeError(
            f"Generation {gen_id!r}: count mismatch "
            f"(actual {actual} vs manifest {expected})")
    if sum(actual.values()) == 0:
        raise RuntimeError(f"Generation {gen_id!r}: empty staged collection")
    return True
