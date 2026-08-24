"""Read-only ERPNext live-API client (Phase 5).

SECURITY.md is explicit: this tool is READ-ONLY until a separate, confirmed
decision says otherwise — so the module exposes GET operations and nothing
else; there is no post/put/delete helper to misuse. Least privilege in the
most literal form available: the capability doesn't exist here.

Credentials come from the environment (.env, gitignored): ERPNEXT_BASE_URL,
ERPNEXT_API_KEY, ERPNEXT_API_SECRET. They are sent only as the request
Authorization header and are never logged or included in error payloads.

Frappe REST shapes used (v15/v16):
  GET /api/resource/DocType/{doctype}        -> full DocType document
  GET /api/resource/{doctype}/{name}         -> one document
  GET /api/resource/{doctype}?filters=...&fields=...&limit_page_length=...
"""

import json
import os
from typing import Any
from urllib.parse import quote

import requests

import config


class ErpnextError(Exception):
    """Base for ERPNext tool failures (fail loud, never silent-degrade)."""


class ErpnextUnavailable(ErpnextError):
    """Instance unreachable / timed out / misconfigured."""


class ErpnextApiError(ErpnextError):
    """ERPNext answered with a non-200 status."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"ERPNext returned {status}: {detail}")
        self.status = status


def _credentials() -> tuple[str, str, str]:
    base = os.environ.get("ERPNEXT_BASE_URL", "").rstrip("/")
    key = os.environ.get("ERPNEXT_API_KEY", "")
    secret = os.environ.get("ERPNEXT_API_SECRET", "")
    if not (base and key and secret):
        raise ErpnextUnavailable(
            "ERPNext tool not configured: set ERPNEXT_BASE_URL, "
            "ERPNEXT_API_KEY, ERPNEXT_API_SECRET in .env"
        )
    return base, key, secret


def _get(path_segment_quoted: str, params: dict[str, Any] | None = None) -> dict:
    """One authorized GET against the configured instance.

    Only ever speaks HTTP GET — enforced by construction (requests.get).
    """
    base, key, secret = _credentials()
    url = f"{base}/api/resource/{path_segment_quoted}"
    try:
        response = requests.get(
            url,
            params=params,
            headers={"Authorization": f"token {key}:{secret}"},
            timeout=config.ERPNEXT_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise ErpnextUnavailable(
            f"ERPNext did not answer within {config.ERPNEXT_TIMEOUT_SECONDS}s"
        ) from exc
    except requests.RequestException as exc:
        raise ErpnextUnavailable(f"ERPNext unreachable: {exc}") from exc

    if len(response.content) > config.ERPNEXT_MAX_RESPONSE_BYTES:
        raise ErpnextApiError(
            413,
            f"payload {len(response.content)} bytes exceeds "
            f"{config.ERPNEXT_MAX_RESPONSE_BYTES}; narrow your query",
        )
    if response.status_code != 200:
        # Server error bodies may echo request data; keep only a short
        # server-provided message and never the auth material.
        try:
            detail = response.json().get("_server_messages", "") or response.text
        except (ValueError, AttributeError):
            detail = response.text
        raise ErpnextApiError(response.status_code, str(detail)[:300])
    try:
        return response.json()
    except ValueError as exc:
        raise ErpnextApiError(502, "non-JSON body from ERPNext") from exc


def _quote_segment(value: str, field: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ErpnextApiError(400, f"{field} must be a non-empty string")
    # safe="" so '/' and '..' cannot form path segments
    return quote(value, safe="")


def get_doctype_schema(doctype: str) -> dict[str, Any]:
    """Full DocType document: fields table, permissions, naming, etc."""
    payload = _get(f"DocType/{_quote_segment(doctype, 'doctype')}")
    return {"doctype": doctype, "data": payload.get("data", payload)}


def get_document(doctype: str, name: str) -> dict[str, Any]:
    """One live document by exact name."""
    segment = f"{_quote_segment(doctype, 'doctype')}/" \
              f"{_quote_segment(name, 'name')}"
    payload = _get(segment)
    return {"doctype": doctype, "name": name, "data": payload.get("data", payload)}


def list_documents(
    doctype: str,
    filters: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    limit: int = config.ERPNEXT_DEFAULT_LIST_LIMIT,
    order_by: str | None = None,
) -> dict[str, Any]:
    """Filtered list of light documents (name + requested fields)."""
    limit = max(1, min(int(limit), config.ERPNEXT_MAX_LIST_LIMIT))
    params: dict[str, Any] = {
        "limit_page_length": limit,
        # stable, predictable output; names alone are useless, full docs too big
        "fields": json.dumps(fields or ["name"]),
    }
    if filters:
        params["filters"] = json.dumps(filters)
    if order_by:
        params["order_by"] = order_by
    payload = _get(_quote_segment(doctype, "doctype"), params=params)
    rows = payload.get("data", payload)
    return {
        "doctype": doctype,
        "count": len(rows) if isinstance(rows, list) else None,
        "rows": rows,
        "limit": limit,
    }
