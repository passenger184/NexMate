"""ACL-aware retrieval integration tests (M4 negative/positive suites).

Run: .venv/bin/python -m unittest discover -s tests -v

Two layers:
1. Real Chroma filtering (temporary persistent collection, fake vectors):
   proves scope predicates exclude denied chunks inside the vector pools.
2. Full retrieve() with real embeddings (skipped when the cached model is
   unavailable): proves end-to-end candidate exclusion, provenance, and
   legacy public-only degradation on fixture corpora.

Fixtures are synthetic; no real private data anywhere.
"""

import tempfile
import unittest
from unittest import mock

import chromadb

from rag import acl
from rag import retriever


SITE = "frontend"
FULL_SCOPE = {"site": SITE, "tiers": ["public", "site", "restricted"],
              "roles": ["Engineer"], "derived_by": "frappe-gateway"}
NARROW_SCOPE = {"site": SITE, "tiers": ["public", "site"], "roles": [],
                "derived_by": "frappe-gateway"}
PUBLIC_SCOPE = {"site": SITE, "tiers": ["public"], "roles": [],
                "derived_by": "frappe-gateway"}

DOCS = [
    ("pub", "public framework documentation about doctypes",
     {"title": "t", "section": "s", "url_or_path": "pub",
      "source_type": "public_doc", "site": "", "visibility": "public"}),
    ("own", "company deployment runbook for this site",
     {"title": "t", "section": "s", "url_or_path": "own",
      "source_type": "company_doc", "site": SITE, "visibility": "site"}),
    ("xsite", "other site secret migration plan",
     {"title": "t", "section": "s", "url_or_path": "xsite",
      "source_type": "company_doc", "site": "other", "visibility": "site"}),
    ("restr", "restricted release checklist for engineers",
     {"title": "t", "section": "s", "url_or_path": "restr",
      "source_type": "our_code", "site": SITE, "visibility": "restricted",
      "allowed_roles": ["Engineer"]}),
    ("restr-no", "restricted payroll export script",
     {"title": "t", "section": "s", "url_or_path": "restr-no",
      "source_type": "our_code", "site": SITE, "visibility": "restricted",
      "allowed_roles": ["Payroll"]}),
    ("unstamped", "legacy chunk without acl metadata",
     {"title": "t", "section": "s", "url_or_path": "unstamped",
      "source_type": "company_doc"}),
]


def make_collection(path, embed=None):
    client = chromadb.PersistentClient(path=str(path))
    try:
        client.delete_collection("m4-fixtures")
    except Exception:
        pass
    col = client.create_collection("m4-fixtures")
    texts = [d[1] for d in DOCS]
    if embed is None:
        vectors = [[float(i), 0.0, 0.0, 0.0] for i in range(len(DOCS))]
    else:
        vectors = [embed.get_text_embedding(t) for t in texts]
    col.add(ids=[d[0] for d in DOCS],
            documents=texts,
            embeddings=vectors,
            metadatas=[d[2] for d in DOCS])
    return col


class VectorPoolScopeTest(unittest.TestCase):
    """Real Chroma where-clauses: denied chunks never enter pools."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.collection = make_collection(self._tmp.name + "/chroma")
        patcher = mock.patch.object(retriever, "get_chroma_collection",
                                    return_value=self.collection)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _pool_ids(self, scope):
        rows = retriever._vector_pool([1.0, 0.0, 0.0, 0.0],
                                      acl.scope_where(scope), 10)
        return sorted(r["url_or_path"] for r in rows)

    def test_full_scope_sees_only_permitted(self) -> None:
        self.assertEqual(self._pool_ids(FULL_SCOPE),
                         ["own", "pub", "restr"])

    def test_narrow_scope_drops_restricted(self) -> None:
        self.assertEqual(self._pool_ids(NARROW_SCOPE), ["own", "pub"])

    def test_public_scope_and_legacy_see_only_public(self) -> None:
        self.assertEqual(self._pool_ids(PUBLIC_SCOPE), ["pub"])
        self.assertEqual(
            self._pool_ids(acl.legacy_public_scope()), ["pub"])

    def test_cross_site_and_unstamped_never_match(self) -> None:
        for scope in (FULL_SCOPE, NARROW_SCOPE, PUBLIC_SCOPE):
            ids = self._pool_ids(scope)
            self.assertNotIn("xsite", ids)
            self.assertNotIn("unstamped", ids)


def _load_embed_or_skip(testcase):
    try:
        import config
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        return HuggingFaceEmbedding(model_name=config.EMBEDDING_MODEL_NAME)
    except Exception as exc:
        testcase.skipTest(f"embedding model unavailable: {exc}")


class FullRetrieveScopeTest(unittest.TestCase):
    """End-to-end retrieve() with real embeddings on fixture corpora."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        model = _load_embed_or_skip(self)
        self.collection = make_collection(self._tmp.name + "/chroma",
                                          embed=model)
        for patcher in (
                mock.patch.object(retriever, "get_chroma_collection",
                                  return_value=self.collection),
                mock.patch.object(retriever, "_get_embed_model",
                                  return_value=model)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _retrieve_paths(self, question, scope):
        from rag.keyword_index import KeywordIndex
        dumped = self.collection.get(include=["documents", "metadatas"])
        with mock.patch.object(retriever, "get_keyword_index",
                               return_value=KeywordIndex(
                                   dumped["ids"], dumped["documents"],
                                   dumped["metadatas"])):
            rows = retriever.retrieve(question, k=6, scope=scope)
        return rows

    def test_denied_content_absent_from_candidates(self) -> None:
        rows = self._retrieve_paths("migration plan checklist", FULL_SCOPE)
        paths = [r["url_or_path"] for r in rows]
        self.assertNotIn("xsite", paths)
        self.assertNotIn("restr-no", paths)
        self.assertNotIn("unstamped", paths)

    def test_provenance_present_on_results(self) -> None:
        rows = self._retrieve_paths("doctypes", FULL_SCOPE)
        self.assertTrue(rows)
        for row in rows:
            for key in ("site", "visibility", "generation"):
                self.assertIn(key, row)

    def test_legacy_direct_is_public_only(self) -> None:
        rows = self._retrieve_paths("runbook", None)
        paths = [r["url_or_path"] for r in rows]
        self.assertNotIn("own", paths)
        self.assertNotIn("xsite", paths)


if __name__ == "__main__":
    unittest.main()
