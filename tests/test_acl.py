"""Unit tests for the M4 coarse-grained ACL contract (rag/acl.py).

Run: .venv/bin/python -m unittest discover -s tests -v

The contract is deliberately narrow: site + visibility tier +
allowed_roles, enforced pre-retrieval. These tests pin the schema freeze
(task 1.1), the predicate semantics, and the fail-closed boundaries —
including that retrieval success never implies ERPNext permission (there
is no DocType/field/permlevel notion anywhere in this module).
"""

import unittest

from rag import acl


SITE = "frontend"
FULL_SCOPE = {"site": SITE, "tiers": ["public", "site", "restricted"],
              "roles": ["Engineer"], "derived_by": "frappe-gateway"}
PUBLIC_SCOPE = {"site": SITE, "tiers": ["public"], "roles": [],
                "derived_by": "frappe-gateway"}


def chunk(site="", visibility="public", allowed_roles=None, **extra):
    meta = {"title": "t", "section": "s", "url_or_path": "u",
            "source_type": "public_doc", "site": site,
            "visibility": visibility,
            "allowed_roles": list(allowed_roles or [])}
    meta.update(extra)
    return meta


class ScopeValidationTest(unittest.TestCase):
    def test_valid_scopes(self) -> None:
        self.assertTrue(acl.valid_scope(FULL_SCOPE))
        self.assertTrue(acl.valid_scope(PUBLIC_SCOPE))
        self.assertTrue(acl.valid_scope(acl.legacy_public_scope()))

    def test_invalid_scopes(self) -> None:
        base = dict(FULL_SCOPE)
        cases = [
            None, [], "scope", {},
            dict(base, tiers=[]),
            dict(base, tiers=["public", "secret"]),
            dict(base, tiers="public"),
            dict(base, roles="Engineer"),
            dict(base, roles=[""]),
            dict(base, site=""),
            dict(base, site=None),
            dict(base, derived_by="browser"),
            dict(base, derived_by="legacy-direct"),
            dict(base, extra="field"),
            {k: v for k, v in base.items() if k != "site"},
        ]
        for scope in cases:
            with self.subTest(scope=str(scope)[:60]):
                self.assertFalse(acl.valid_scope(scope))

    def test_legacy_scope_is_public_only(self) -> None:
        legacy = acl.legacy_public_scope()
        self.assertEqual(legacy["tiers"], ["public"])
        self.assertEqual(legacy["roles"], [])
        self.assertIsNone(legacy["site"])


class PredicateTest(unittest.TestCase):
    def test_cross_site_excluded(self) -> None:
        self.assertFalse(acl.match_metadata(
            chunk(site="other", visibility="site"), FULL_SCOPE))

    def test_own_site_tiers(self) -> None:
        self.assertTrue(acl.match_metadata(
            chunk(site="", visibility="public"), FULL_SCOPE))
        self.assertTrue(acl.match_metadata(
            chunk(site=SITE, visibility="site"), FULL_SCOPE))
        # Public tier is global: chunk site never blocks it.
        self.assertTrue(acl.match_metadata(
            chunk(site="anywhere", visibility="public"), FULL_SCOPE))

    def test_restricted_needs_role_overlap(self) -> None:
        ok = chunk(site=SITE, visibility="restricted",
                   allowed_roles=["Engineer", "Other"])
        denied = chunk(site=SITE, visibility="restricted",
                       allowed_roles=["Other"])
        self.assertTrue(acl.match_metadata(ok, FULL_SCOPE))
        self.assertFalse(acl.match_metadata(denied, FULL_SCOPE))
        self.assertFalse(acl.match_metadata(ok, PUBLIC_SCOPE))

    def test_unstamped_chunks_unreachable_even_for_admin(self) -> None:
        admin = {"site": SITE, "tiers": ["public", "site", "restricted"],
                 "roles": ["Administrator", "System Manager"],
                 "derived_by": "frappe-gateway"}
        for meta in ({"source_type": "our_code"},
                     chunk(site=SITE, visibility="topsecret"),
                     chunk(site=SITE, visibility="restricted",
                           allowed_roles="Engineer"),
                     "not-a-dict", None):
            with self.subTest(meta=str(meta)[:50]):
                self.assertFalse(acl.match_metadata(meta, admin))

    def test_chroma_where_matches_python_predicate(self) -> None:
        # Spot-check the compiled where clause against representative metas.
        import chromadb
        client = chromadb.Client()
        col = client.create_collection("acl-spot")
        metas = [
            chunk(site="", visibility="public"),
            chunk(site=SITE, visibility="site"),
            chunk(site="other", visibility="site"),
            chunk(site=SITE, visibility="restricted",
                  allowed_roles=["Engineer"]),
            chunk(site=SITE, visibility="restricted",
                  allowed_roles=["Other"]),
            {"source_type": "our_code"},
        ]
        col.add(ids=[f"d{i}" for i in range(len(metas))],
                documents=["text"] * len(metas),
                metadatas=[{k: v for k, v in m.items() if k != "allowed_roles"
                            or v} if isinstance(m, dict) else m
                           for m in metas])
        got = col.get(where=acl.scope_where(FULL_SCOPE))
        self.assertEqual(sorted(got["ids"]), ["d0", "d1", "d3"])
        got_public = col.get(where=acl.scope_where(PUBLIC_SCOPE))
        self.assertEqual(got_public["ids"], ["d0"])
        got_legacy = col.get(where=acl.scope_where(acl.legacy_public_scope()))
        self.assertEqual(got_legacy["ids"], ["d0"])
        for meta in metas:
            if isinstance(meta, dict):
                self.assertEqual(
                    acl.match_metadata(meta, FULL_SCOPE),
                    meta.get("visibility") in ("public", "site")
                    and (meta.get("visibility") == "public"
                         or meta.get("site") == SITE)
                    or (meta.get("visibility") == "restricted"
                        and meta.get("site") == SITE
                        and "Engineer" in meta.get("allowed_roles", [])))

    def test_empty_scope_matches_nothing(self) -> None:
        nowhere = {"site": SITE, "tiers": [], "roles": [],
                   "derived_by": "frappe-gateway"}
        where = acl.scope_where(nowhere)
        self.assertNotIn("d0", where)


class StampingTest(unittest.TestCase):
    def test_corpus_defaults(self) -> None:
        self.assertEqual(
            acl.stamp_metadata({}, "public_doc"),
            {"site": "", "visibility": "public"})
        stamped = acl.stamp_metadata({}, "our_code", SITE)
        self.assertEqual(stamped["site"], SITE)
        self.assertEqual(stamped["visibility"], "site")
        self.assertNotIn("allowed_roles", stamped)
        # Company content without a site stamps unreachable-by-design.
        blind = acl.stamp_metadata({}, "company_doc", "")
        self.assertEqual(blind["site"], "")
        self.assertFalse(acl.match_metadata(
            dict(blind, title="t", section="s", url_or_path="u"),
            FULL_SCOPE))

    def test_build_time_rejection(self) -> None:
        class Node:
            def __init__(self, metadata):
                self.metadata = metadata

        acl.assert_stamped([Node(chunk())])
        with self.assertRaises(RuntimeError):
            acl.assert_stamped([Node({"title": "t"})])


class IngestionStampingTest(unittest.TestCase):
    def test_project_pipeline_stamps_every_chunk(self) -> None:
        from ingestion.ingest_project import load_project_documents
        docs, counts = load_project_documents(dry_run=True, site="frontend")
        self.assertTrue(docs)
        acl.assert_stamped(docs)
        seen = {d.metadata["source_type"] for d in docs}
        self.assertTrue(seen <= {"our_code", "company_doc"})
        for doc in docs:
            self.assertEqual(doc.metadata["site"], "frontend")
            self.assertEqual(doc.metadata["visibility"], "site")


if __name__ == "__main__":
    unittest.main()
