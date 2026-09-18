"""Unit tests for versioned index generations (rag/generations.py).

Run: .venv/bin/python -m unittest discover -s tests -v

All filesystem state lives in a temporary directory; the real data dir is
never touched. Covers task 1.3 (record format) and the lifecycle contract:
staged builds, atomic publication, rollback, fingerprint gating.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from rag import generations


FP = {"model": "m", "revision": "r1", "dimensions": 4, "metric": "cosine"}


class GenerationLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(config, "GENERATIONS_DIR",
                                    Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _manifest(self, gen_id="gen-1", **over):
        args = {"parent": None, "sources": {"public": "rev1"},
                "fingerprint": dict(FP), "acl_schema_version": 1,
                "counts": {"public_doc": 10}}
        args.update(over)
        return generations.write_manifest(gen_id, **args)

    def test_record_format_and_roundtrip(self) -> None:
        manifest = self._manifest()
        self.assertEqual(manifest["id"], "gen-1")
        self.assertEqual(manifest["embedding_fingerprint"], FP)
        self.assertEqual(generations.read_manifest("gen-1"), manifest)

    def test_unknown_generation_fails_loud(self) -> None:
        with self.assertRaises(RuntimeError):
            generations.read_manifest("gen-nope")

    def test_no_pointer_means_legacy(self) -> None:
        self.assertIsNone(generations.active_generation_id())

    def test_publish_and_rollback(self) -> None:
        self._manifest("gen-1")
        self._manifest("gen-2", parent="gen-1")
        calls = []

        def verify():
            calls.append(True)
            return True

        generations.publish_generation("gen-2", verify)
        self.assertEqual(generations.active_generation_id(), "gen-2")
        self.assertEqual(calls, [True])
        rolled = generations.rollback_generation()
        self.assertEqual(rolled["id"], "gen-1")
        self.assertEqual(generations.active_generation_id(), "gen-1")

    def test_failed_verification_never_publishes(self) -> None:
        self._manifest("gen-1")
        with self.assertRaises(RuntimeError):
            generations.publish_generation("gen-1", lambda: False)
        self.assertIsNone(generations.active_generation_id())

    def test_rollback_from_first_generation_returns_legacy(self) -> None:
        self._manifest("gen-1")
        generations.publish_generation("gen-1", lambda: True)
        rolled = generations.rollback_generation()
        self.assertTrue(rolled.get("legacy"))
        self.assertEqual(generations.active_generation_id(),
                         generations.LEGACY_GENERATION_ID)

    def test_rollback_with_nothing_published_fails(self) -> None:
        with self.assertRaises(RuntimeError):
            generations.rollback_generation()

    def test_revoked_generation_refuses_rollback(self) -> None:
        self._manifest("gen-1")
        self._manifest("gen-2", parent="gen-1")
        generations.publish_generation("gen-2", lambda: True)
        self.assertFalse(generations.is_revoked("gen-1"))
        generations.revoke_generation("gen-1", reason="acl-test")
        self.assertTrue(generations.is_revoked("gen-1"))
        with self.assertRaises(RuntimeError):
            generations.rollback_generation()
        # Active generation is untouched by the refused rollback.
        self.assertEqual(generations.active_generation_id(), "gen-2")
        with self.assertRaises(RuntimeError):
            generations.publish_generation("gen-1", lambda: True)
        self.assertEqual(generations.active_generation_id(), "gen-2")

    def test_revoke_unknown_generation_fails_loud(self) -> None:
        with self.assertRaises(RuntimeError):
            generations.revoke_generation("gen-nope")
        with self.assertRaises(ValueError):
            generations.revoke_generation(generations.LEGACY_GENERATION_ID)

    def test_fingerprint_matrix(self) -> None:
        same = dict(FP)
        self.assertTrue(generations.fingerprint_compatible(same, dict(FP)))
        for field, value in (("model", "other"), ("dimensions", 8),
                             ("metric", "l2")):
            bad = dict(FP, **{field: value})
            self.assertFalse(generations.fingerprint_compatible(bad, dict(FP)))
            self.assertFalse(generations.fingerprint_compatible(dict(FP), bad))
        # Unknown revisions never block; known mismatch refuses.
        self.assertTrue(generations.fingerprint_compatible(
            dict(FP, revision="unknown"), dict(FP)))
        self.assertTrue(generations.fingerprint_compatible(
            dict(FP), dict(FP, revision="unknown")))
        self.assertFalse(generations.fingerprint_compatible(
            dict(FP, revision="r2"), dict(FP)))

    def test_manifest_requires_full_fingerprint(self) -> None:
        with self.assertRaises(ValueError):
            self._manifest("gen-bad", fingerprint={"model": "m"})

    def test_pointer_is_atomic_json(self) -> None:
        self._manifest("gen-1")
        generations.publish_generation("gen-1", lambda: True)
        pointer = Path(self._tmp.name) / config.GENERATION_ACTIVE_POINTER
        self.assertEqual(json.loads(pointer.read_text())["active"], "gen-1")


class StagedBuildTest(unittest.TestCase):
    """Staged collections, backfill migration, and publication verification."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        import chromadb
        self.client = chromadb.PersistentClient(
            path=self._tmp.name + "/chroma")
        try:
            self.client.delete_collection("erpnext_docs")
        except Exception:
            pass
        col = self.client.create_collection("erpnext_docs")
        col.add(
            ids=["p1", "p2", "c1"],
            documents=["public text", "more public text", "company text"],
            embeddings=[[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]],
            metadatas=[
                {"source_type": "public_doc"},
                {"source_type": "public_doc"},
                {"source_type": "company_doc"},
            ])
        patcher = mock.patch.object(config, "GENERATIONS_DIR",
                                    Path(self._tmp.name) / "generations")
        patcher.start()
        self.addCleanup(patcher.stop)
        client_patcher = mock.patch.object(
            generations, "_client", return_value=self.client)
        client_patcher.start()
        self.addCleanup(client_patcher.stop)

    def test_backfill_stamps_without_reembed(self) -> None:
        before = self.client.get_collection("erpnext_docs").get(
            include=["embeddings"])
        counts = generations.backfill_acl_metadata(
            "erpnext_docs", "frontend",
            backup_path=self._tmp.name + "/backup.jsonl")
        self.assertEqual(counts, {"public": 2, "site": 1})
        after = self.client.get_collection("erpnext_docs").get(
            include=["embeddings", "metadatas"])
        self.assertEqual(
            [list(map(float, v)) for v in after["embeddings"]],
            [list(map(float, v)) for v in before["embeddings"]])
        by_id = dict(zip(after["ids"], after["metadatas"]))
        self.assertEqual(by_id["p1"]["visibility"], "public")
        self.assertEqual(by_id["p1"]["site"], "")
        self.assertEqual(by_id["c1"]["visibility"], "site")
        self.assertEqual(by_id["c1"]["site"], "frontend")
        with open(self._tmp.name + "/backup.jsonl", encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
        self.assertEqual(len(rows), 3)
        self.assertNotIn("visibility", rows[0]["metadata"])

    def test_backfill_refuses_empty_site(self) -> None:
        with self.assertRaises(ValueError):
            generations.backfill_acl_metadata("erpnext_docs", "")

    def test_scoped_rebuild_preserves_unrelated_corpora(self) -> None:
        generations.backfill_acl_metadata("erpnext_docs", "frontend")
        copied = generations.seed_staged_from(
            "erpnext_docs--gen-1", None, drop_source_types=("public_doc",))
        self.assertEqual(copied, 1)
        staged = self.client.get_collection("erpnext_docs--gen-1")
        got = staged.get(include=["metadatas"])
        self.assertEqual(
            [m["source_type"] for m in got["metadatas"]], ["company_doc"])

    def test_verify_generation_checks_counts_and_fingerprint(self) -> None:
        generations.backfill_acl_metadata("erpnext_docs", "frontend")
        generations.seed_staged_from("erpnext_docs--gen-1", None)
        fp = {"model": "m", "revision": "r1", "dimensions": 4,
              "metric": "cosine"}
        generations.write_manifest(
            "gen-1", parent=None, sources={"public": "r", "project": "r"},
            fingerprint=fp, acl_schema_version=1,
            counts={"public_doc": 2, "company_doc": 1})
        self.assertTrue(generations.verify_generation("gen-1", dict(fp)))
        with self.assertRaises(RuntimeError):
            generations.verify_generation(
                "gen-1", dict(fp, dimensions=8))
        generations.write_manifest(
            "gen-bad", parent=None, sources={}, fingerprint=fp,
            acl_schema_version=1, counts={"public_doc": 999})
        with self.assertRaises(RuntimeError):
            generations.verify_generation("gen-bad", dict(fp))

    def test_keyword_snapshot_follows_generations(self) -> None:
        from rag import keyword_index

        class FakeCollection:
            def __init__(self, docs):
                self._docs = docs

            def get(self, include=None):
                return {"ids": [f"d{i}" for i in range(len(self._docs))],
                        "documents": list(self._docs),
                        "metadatas": [{} for _ in self._docs]}

        with mock.patch.object(
                keyword_index, "_collection_for_generation",
                side_effect=lambda gen: (FakeCollection(["alpha one"]), gen)):
            keyword_index.invalidate_keyword_index()
            first = keyword_index.get_keyword_index("gen-1")
            same = keyword_index.get_keyword_index("gen-1")
            self.assertIs(first, same)
        with mock.patch.object(
                keyword_index, "_collection_for_generation",
                side_effect=lambda gen: (FakeCollection(["beta two"]), gen)):
            second = keyword_index.get_keyword_index("gen-2")
            self.assertIsNot(first, second)
            self.assertEqual(second.search("beta", 5)[0]["bm25_score"] > 0,
                             True)
            self.assertEqual(first.search("beta", 5), [])
        keyword_index.invalidate_keyword_index()


if __name__ == "__main__":
    unittest.main()
