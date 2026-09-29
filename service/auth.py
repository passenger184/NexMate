import hmac
import json
import logging
import re
import unicodedata

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

import config

logger = logging.getLogger("nexmate.auth")


def valid_service_key(value: object) -> bool:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        return False
    lowered = value.lower()
    return not any(lowered == lowered[:size] * (64 // size)
                   for size in (1, 2, 4, 8, 16, 32))


def valid_identity(value: object) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 255
            and value == value.strip()
            and not any(unicodedata.category(char).startswith("C")
                        for char in value))


CONVERSATION_ID_PATTERN = r"[A-Za-z0-9_.~@-]{1,140}"
# Wire budget mirrors the prompt-budget constants in config.py with headroom
# for in-flight threads; Frappe enforces the tighter forward budget.
CONVERSATION_MAX_TURNS = config.SESSION_MAX_TURNS * 4
CONVERSATION_MAX_CHARS = config.SESSION_MAX_CHARS * 4
CONVERSATION_TURN_KEYS = frozenset({"role", "content"})
CONVERSATION_KEYS = frozenset({"id", "owner", "site", "turns"})


def valid_conversation_id(value: object) -> bool:
    # Identical rule to the Frappe side: only identifiers the gateway could
    # have minted are structurally acceptable.
    return (isinstance(value, str)
            and re.fullmatch(CONVERSATION_ID_PATTERN, value) is not None)


def _valid_turn(turn: object) -> bool:
    return (isinstance(turn, dict)
            and set(turn) == CONVERSATION_TURN_KEYS
            and turn.get("role") in ("user", "assistant")
            and isinstance(turn.get("content"), str)
            and 0 < len(turn["content"]) <= CONVERSATION_MAX_CHARS)


def validate_conversation_block(conv: object, user: str) -> list[dict[str, str]]:
    """Consistency validation for a Frappe-supplied conversation block.

    Frappe is authoritative for user identity, site, and conversation
    ownership; this check NEVER authorizes ownership itself. It only
    confirms the block is well-formed and internally consistent with the
    already-validated envelope (owner equals envelope user, site equals
    the trusted site) and within wire budget. Anything else fails loud
    with a safe code and no data. Returns normalized turns.
    """
    if (not isinstance(conv, dict) or set(conv) != CONVERSATION_KEYS
            or not valid_conversation_id(conv.get("id"))):
        raise HTTPException(status_code=422, detail="invalid_conversation_context")
    if conv.get("owner") != user:
        raise HTTPException(status_code=422, detail="invalid_conversation_context")
    if (not valid_identity(config.NEXMATE_FRAPPE_SITE)
            or conv.get("site") != config.NEXMATE_FRAPPE_SITE):
        raise HTTPException(status_code=422, detail="invalid_conversation_context")
    turns = conv.get("turns")
    if not isinstance(turns, list) or len(turns) > CONVERSATION_MAX_TURNS:
        raise HTTPException(status_code=422, detail="invalid_conversation_context")
    total = 0
    for turn in turns:
        if not _valid_turn(turn):
            raise HTTPException(status_code=422, detail="invalid_conversation_context")
        total += len(turn["content"])
    if total > CONVERSATION_MAX_CHARS:
        raise HTTPException(status_code=422, detail="invalid_conversation_context")
    return [{"role": turn["role"], "content": turn["content"]} for turn in turns]


SCOPE_KEYS = frozenset({"site", "tiers", "roles", "derived_by"})
SCOPE_TIERS = ("public", "site", "restricted")
SCOPE_DERIVED_BY_MARKER = "frappe-gateway"

#: The single generic authenticated execution scope. It asserts only that a
#: credentialed, Frappe-attributed request may reach orchestration. It grants
#: no ERPNext access, no metadata access, no write access, no code execution,
#: and no tool execution; each of those is separately gated (design D1).
EXECUTION_SCOPE_AUTHENTICATED = "frappe-attributed"

# --- U5 authorized ERPNext context ----------------------------------------
# Inference CONSUMES this Frappe-produced, already-authorized data. It is
# structure-checked here so a malformed or oversized payload cannot be used.
# This check NEVER grants authorization; Frappe already performed it.
AUTHORIZED_CONTEXT_KEYS = frozenset({"doctype", "operation", "fields_returned", "row_count", "data"})
AUTHORIZED_CONTEXT_OPERATIONS = ("document", "list")
#: Immutable service ceilings for business-read payloads, mirroring the
#: producer's approved immutable ceilings in ``erpnext_read.py``
#: (``MAX_LIST_LIMIT``, ``MAX_FIELD_COUNT``, ``MAX_RESULT_BYTES``).
#:
#: A consumer must never be NARROWER than its producer: the Frappe control
#: plane resolves each bound to ``min(administrator value, service ceiling)``
#: and admits anything up to the ceiling, so a payload this validator refused
#: would be a Frappe-authorized read the assistant silently lost. These are
#: ceilings, not administrator settings — narrowing still happens upstream in
#: ``NexMate Settings``, and the defaults (20 rows / 20 fields / 64 KiB) are
#: what applies until an administrator raises them.
MAX_AUTHORIZED_CONTEXT_ROWS = 100
MAX_AUTHORIZED_CONTEXT_FIELDS = 50
MAX_AUTHORIZED_CONTEXT_BYTES = 131072

# --- Capability- and policy-gated metadata --------------------------------
# Metadata is a SEPARATE contract from the business read, not a new business
# read. It is admitted alongside the existing keys with its own declared shape
# and its own bounds, so the two contracts are never merged (design D11).
METADATA_CONTEXT_KEYS = frozenset({"doctype", "operation", "field_count", "fields"})
METADATA_OPERATION = "schema"
#: Immutable service ceilings for metadata payloads. These are deliberately
#: SEPARATE constants from the business-read bounds above, even where values
#: could coincide: sharing one constant would re-couple the two contracts.
#: They are ceilings, not administrator settings — the Frappe control plane
#: resolves the effective (possibly narrower) bounds per decision, and this
#: validator accepts anything within the ceilings so a Frappe-accepted payload
#: is never rejected here with HTTP 422.
METADATA_FIELDS_CEILING = 500
METADATA_BYTES_CEILING = 131072
#: Closed projection. Inference may not widen or narrow this: the control plane
#: produced it, and anything outside these attributes did not come from the
#: declared five-field projection.
METADATA_PROJECTION_KEYS = frozenset({"fieldname", "fieldtype", "label", "reqd", "read_only"})


def validate_metadata_context(context: object) -> dict:
    """Structure and bound validation for Frappe-produced metadata context.

    Frappe is authoritative for the metadata decision; this check never grants
    it. It confirms the declared shape, a supported operation, bounded field
    count and size, and that every projected entry carries exactly the
    five declared structural attributes and no business data.
    """
    if not isinstance(context, dict) or set(context) != METADATA_CONTEXT_KEYS:
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    if context.get("operation") != METADATA_OPERATION:
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    doctype = context.get("doctype")
    if not isinstance(doctype, str) or not doctype or len(doctype) > 140:
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    field_count = context.get("field_count")
    if (not isinstance(field_count, int) or isinstance(field_count, bool)
            or field_count < 0 or field_count > METADATA_FIELDS_CEILING):
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    fields = context.get("fields")
    if not isinstance(fields, list) or len(fields) > METADATA_FIELDS_CEILING:
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    if len(fields) != field_count:
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    for entry in fields:
        if not isinstance(entry, dict) or set(entry) != METADATA_PROJECTION_KEYS:
            raise HTTPException(status_code=422, detail="invalid_authorized_context")
        if not all(isinstance(entry.get(k), (str, bool, int))
                   for k in METADATA_PROJECTION_KEYS):
            raise HTTPException(status_code=422, detail="invalid_authorized_context")
    if len(json.dumps(context, default=str)) > METADATA_BYTES_CEILING:
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    return context


def validate_authorized_context(context: object) -> dict:
    """Structure and bound validation for Frappe-produced authorized data.

    Frappe is authoritative for the authorization decision; this check never
    grants it. It confirms the frozen shape, a supported operation, bounded
    field/row counts and a bounded serialized size, and rejects anything that
    looks like a credential or an authorization-subject override.

    A metadata context is a distinct contract with its own declared shape and
    bounds, dispatched here rather than widening the business-read contract.
    The business-read bounds are the producer's approved immutable ceilings
    (100 rows / 50 fields / 131072 bytes), not administrator settings: the
    effective, possibly narrower, limits are resolved by the Frappe control
    plane before a payload ever reaches here.
    """
    if (isinstance(context, dict)
            and context.get("operation") == METADATA_OPERATION):
        return validate_metadata_context(context)
    if not isinstance(context, dict) or set(context) != AUTHORIZED_CONTEXT_KEYS:
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    if context.get("operation") not in AUTHORIZED_CONTEXT_OPERATIONS:
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    doctype = context.get("doctype")
    if not isinstance(doctype, str) or not doctype or len(doctype) > 140:
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    fields_returned = context.get("fields_returned")
    if (not isinstance(fields_returned, list)
            or len(fields_returned) > MAX_AUTHORIZED_CONTEXT_FIELDS
            or not all(isinstance(f, str) and 0 < len(f) <= 140 for f in fields_returned)):
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    row_count = context.get("row_count")
    if row_count is not None and (not isinstance(row_count, int) or row_count < 0
                                  or row_count > MAX_AUTHORIZED_CONTEXT_ROWS):
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    data = context.get("data")
    if context["operation"] == "document":
        if not isinstance(data, dict) or not data:
            raise HTTPException(status_code=422, detail="invalid_authorized_context")
        if not set(data) <= set(fields_returned):
            raise HTTPException(status_code=422, detail="invalid_authorized_context")
    else:
        if not isinstance(data, list) or len(data) > MAX_AUTHORIZED_CONTEXT_ROWS:
            raise HTTPException(status_code=422, detail="invalid_authorized_context")
        for row in data:
            if not isinstance(row, dict) or not set(row) <= set(fields_returned):
                raise HTTPException(status_code=422, detail="invalid_authorized_context")
    if len(json.dumps(context, default=str)) > MAX_AUTHORIZED_CONTEXT_BYTES:
        raise HTTPException(status_code=422, detail="invalid_authorized_context")
    return context


def validate_authz_scope(scope: object, user: str, site: str) -> dict:
    """Consistency validation for a Frappe-derived authorization scope.

    Frappe is authoritative for the scope; this check NEVER grants
    authorization itself. It confirms structure (frozen fields), the
    Frappe-derivation marker, and consistency with the already-validated
    envelope user and trusted site. Anything else fails loud.
    Returns the scope unchanged.
    """
    if (not isinstance(scope, dict) or set(scope) != SCOPE_KEYS
            or not valid_identity(scope.get("site"))
            or scope.get("site") != site
            or scope.get("site") != config.NEXMATE_FRAPPE_SITE):
        raise HTTPException(status_code=422, detail="invalid_authz_scope")
    tiers = scope.get("tiers")
    if (not isinstance(tiers, list) or not tiers
            or any(t not in SCOPE_TIERS for t in tiers)):
        raise HTTPException(status_code=422, detail="invalid_authz_scope")
    roles = scope.get("roles")
    if (not isinstance(roles, list)
            or not all(valid_identity(r) for r in roles)):
        raise HTTPException(status_code=422, detail="invalid_authz_scope")
    if scope.get("derived_by") != SCOPE_DERIVED_BY_MARKER:
        raise HTTPException(status_code=422, detail="invalid_authz_scope")
    if user == "Guest":
        raise HTTPException(status_code=422, detail="invalid_authz_scope")
    return scope


class ServiceAuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["path"] == "/health":
            await JSONResponse({"status": "ok"})(scope, receive, send)
            return
        key = config.NEXMATE_SERVICE_KEY
        environment = config.NEXMATE_ENV
        headers = [value for name, value in scope.get("headers", [])
                   if name.lower() == b"x-nexmate-key"]
        scope.setdefault("state", {})["service_authenticated"] = False
        if environment not in ("production", "development"):
            logger.warning("invalid_service_environment")
        configured = key is not None
        if configured and not valid_service_key(key):
            await self._reject(scope, receive, send, 503, "invalid_service_key_config")
            return
        if headers:
            if not configured:
                await self._reject(scope, receive, send, 503, "service_key_unconfigured")
                return
            if (len(headers) != 1
                    or re.fullmatch(rb"[0-9a-fA-F]{64}", headers[0]) is None
                    or not hmac.compare_digest(headers[0], key.encode("ascii"))):
                await self._reject(scope, receive, send, 401, "invalid_service_credential")
                return
            scope["state"]["service_authenticated"] = True
        elif not (environment == "development"
                  and config.NEXMATE_DEV_UNAUTHENTICATED == "1"):
            code = "service_credential_required" if configured else "service_key_unconfigured"
            await self._reject(scope, receive, send, 401 if configured else 503, code)
            return
        await self.app(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send,
                      status: int, code: str) -> None:
        logger.warning(code)
        await JSONResponse({"detail": code}, status_code=status)(scope, receive, send)


def validate_gateway_envelope(payload: dict, supplied: set[str],
                              request: Request) -> bool:
    envelope_fields = {"user", "site", "execution_scope"}
    if not supplied & envelope_fields:
        # No gateway envelope. Refuse any field that asserts Frappe-derived
        # authorization BEFORE returning, rather than letting it through
        # unvalidated. These are not validated as if a user existed — no user
        # exists to validate them against — they are refused outright.
        if supplied & AUTHORIZATION_BEARING_FIELDS:
            raise HTTPException(status_code=422, detail="unattributed_authorization_state")
        return False
    if not getattr(request.state, "service_authenticated", False):
        raise HTTPException(status_code=401, detail="gateway_credential_required")
    if not envelope_fields.union({"mode"}) <= supplied:
        raise HTTPException(status_code=422, detail="invalid_gateway_envelope")
    if (not valid_identity(payload["user"]) or payload["user"] == "Guest"
            or not valid_identity(payload["site"])
            or payload["mode"] not in ("developer", "employee")
            or payload["execution_scope"] != EXECUTION_SCOPE_AUTHENTICATED):
        raise HTTPException(status_code=422, detail="invalid_gateway_envelope")
    if not valid_identity(config.NEXMATE_FRAPPE_SITE):
        raise HTTPException(status_code=503, detail="invalid_frappe_site_config")
    if payload["site"] != config.NEXMATE_FRAPPE_SITE:
        raise HTTPException(status_code=403, detail="gateway_site_mismatch")
    if "conversation" in supplied and payload.get("conversation") is not None:
        validate_conversation_block(payload["conversation"], payload["user"])
    if "scope" in supplied and payload.get("scope") is not None:
        validate_authz_scope(payload["scope"], payload["user"], payload["site"])
    if "authorized_context" in supplied and payload.get("authorized_context") is not None:
        validate_authorized_context(payload["authorized_context"])
    return True


#: Fields that assert Frappe-derived authorization state. Without a complete,
#: service-authenticated gateway envelope none of them may be supplied: each
#: is independently a way to assert authorization that was never derived from
#: a Frappe session (task 5.3-5.5, design D10).
AUTHORIZATION_BEARING_FIELDS = frozenset({
    "authorized_context", "scope", "conversation",
})
