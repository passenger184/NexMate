"""Coarse-grained knowledge-access control (M4 acl-aware-retrieval).

This is NOT ERPNext/Frappe permission parity: chunks carry a small,
intentionally stamped access label, and retrieval enforces it BEFORE
candidate selection. Retrieval success never proves ERPNext permission on
the underlying source object.

Model:
  site          - owning Frappe site; required except public-tier chunks,
                  which are global (empty site) because public framework
                  docs are identical everywhere.
  visibility    - one of "public" | "site" | "restricted".
  allowed_roles - required (possibly empty list is invalid) iff restricted.

Enforcement predicate (applied to vector pools AND lexical candidates
before fusion):
  public                                            (any scope with public)
  OR (site == scope.site AND (site-tier OR restricted+role overlap))
Chunks missing valid metadata never match (fail closed).
"""

VISIBILITY_TIERS = ("public", "site", "restricted")
ACL_METADATA_FIELDS = ("site", "visibility", "allowed_roles")
DERIVED_BY_MARKER = "frappe-gateway"
LEGACY_DERIVED_BY_MARKER = "legacy-direct"
SCOPE_KEYS = frozenset({"site", "tiers", "roles", "derived_by"})
IMPOSSIBLE_VISIBILITY = "__m4_impossible__"

# Corpus defaults at ingestion time (overridable per ingestion config).
CORPUS_VISIBILITY_DEFAULTS = {
    "public_doc": "public",
    "company_doc": "site",
    "our_code": "site",
    "resolved_issue": "site",
}


def stamp_metadata(metadata: dict, source_type: str, site: str = "") -> dict:
    """Attach ACL metadata to a chunk metadata mapping (in place).

    Public-tier chunks are global (empty site): public framework docs are
    identical everywhere. Company tiers require an explicit site; an empty
    site stamps them unreachable-by-design until re-stamped (fail closed).
    Empty role lists are omitted: Chroma rejects empty-list metadata
    values, and absence already means "no roles" to the predicates.
    """
    visibility = CORPUS_VISIBILITY_DEFAULTS.get(source_type, "site")
    metadata["site"] = "" if visibility == "public" else site
    metadata["visibility"] = visibility
    metadata.pop("allowed_roles", None)
    return metadata


def assert_stamped(nodes) -> None:
    """Build-time rejection of chunks missing valid ACL metadata."""
    for node in nodes:
        meta = node.metadata
        roles = meta.get("allowed_roles")
        if (meta.get("visibility") not in VISIBILITY_TIERS
                or not isinstance(meta.get("site"), str)
                or (meta.get("visibility") == "public" and meta.get("site") != "")
                or (meta.get("visibility") == "restricted"
                    and not (isinstance(roles, list) and roles
                             and all(isinstance(r, str) and r for r in roles)))
                or (roles is not None and not isinstance(roles, list))):
            raise RuntimeError(
                "Chunk missing valid ACL metadata: "
                f"{meta.get('url_or_path', '?')}")


def valid_scope(scope: object) -> bool:
    """Structural check for an authorization-scope mapping."""
    if not isinstance(scope, dict) or set(scope) != SCOPE_KEYS:
        return False
    site, tiers, roles, derived_by = (
        scope.get("site"), scope.get("tiers"),
        scope.get("roles"), scope.get("derived_by"),
    )
    if derived_by not in (DERIVED_BY_MARKER, LEGACY_DERIVED_BY_MARKER):
        return False
    if derived_by == LEGACY_DERIVED_BY_MARKER:
        # The legacy marker is only meaningful on the exact legacy shape;
        # anything else wearing it is contradictory, not structural.
        return (site is None and tiers == ["public"] and roles == [])
    if not isinstance(tiers, list) or not tiers:
        return False
    if any(t not in VISIBILITY_TIERS for t in tiers):
        return False
    if not isinstance(roles, list) or not all(
            isinstance(r, str) and r for r in roles):
        return False
    if site is None:
        # Legacy direct (unscoped) callers: public tier only, no site.
        return (tiers == ["public"] and roles == []
                and derived_by == LEGACY_DERIVED_BY_MARKER)
    if not isinstance(site, str) or not site.strip():
        return False
    return True


def legacy_public_scope() -> dict:
    """Scope for unscopable legacy direct calls: public tier only."""
    return {"site": None, "tiers": ["public"], "roles": [],
            "derived_by": LEGACY_DERIVED_BY_MARKER}


def match_metadata(meta: object, scope: dict) -> bool:
    """Python mirror of the Chroma predicate (BM25 pre-filter + tests)."""
    if not isinstance(meta, dict):
        return False
    visibility = meta.get("visibility")
    if visibility not in scope.get("tiers", ()):
        return False
    if visibility == "public":
        return True
    if meta.get("site") != scope.get("site"):
        return False
    if visibility == "site":
        return True
    if visibility == "restricted":
        allowed = meta.get("allowed_roles")
        return (isinstance(allowed, list)
                and bool(set(allowed) & set(scope.get("roles", []))))
    return False


def scope_where(scope: dict) -> dict:
    """Compile a scope to a Chroma `where` clause (fail closed).

    NOTE: restricted-role matching uses `$contains` (array-element match;
    verified against pinned chromadb==1.5.9). `$in` does NOT match inside
    stored lists — using it here would silently exclude every restricted
    chunk, so the unit suite pins `$contains` behavior explicitly.
    """
    tiers = scope.get("tiers", [])
    roles = scope.get("roles", [])
    branches = []
    if "public" in tiers:
        branches.append({"visibility": "public"})
    site_branches = []
    if "site" in tiers:
        site_branches.append({"visibility": "site"})
    if "restricted" in tiers and roles:
        role_match = [{"allowed_roles": {"$contains": role}} for role in roles]
        site_branches.append({"$and": [
            {"visibility": "restricted"},
            role_match[0] if len(role_match) == 1 else {"$or": role_match},
        ]})
    if site_branches and scope.get("site") is not None:
        scoped = (site_branches[0] if len(site_branches) == 1
                  else {"$or": site_branches})
        branches.append({"$and": [{"site": scope["site"]}, scoped]})
    if not branches:
        return {"visibility": IMPOSSIBLE_VISIBILITY}
    if len(branches) == 1:
        return branches[0]
    return {"$or": branches}
