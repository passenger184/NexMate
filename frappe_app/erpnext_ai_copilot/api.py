import json
import logging
import math
import re
import unicodedata
from urllib.parse import urlsplit

import frappe
import requests


logger = logging.getLogger("nexmate.gateway")
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_QUESTION_CHARS = 2000
CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 300
MAX_INFERENCE_TIMEOUT_SECONDS = 900
ALLOWED_FORM_FIELDS = frozenset({"cmd", "question", "session_id", "mode"})
RESPONSE_FIELDS = (
    "answer", "sources", "confidence", "route", "mode", "session_id", "version_info",
)


def _valid_identity(value: object) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 255
            and value == value.strip()
            and not any(unicodedata.category(char).startswith("C") for char in value))


def _valid_key(value: object) -> bool:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        return False
    lowered = value.lower()
    return not any(lowered == lowered[:size] * (64 // size)
                   for size in (1, 2, 4, 8, 16, 32))


def _inference_url() -> str | None:
    base = frappe.conf.get("copilot_api_base")
    if not isinstance(base, str) or not base or base != base.strip():
        return None
    try:
        parsed = urlsplit(base)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment
                or any(char.isspace() or ord(char) < 32 for char in base)):
            return None
        parsed.port
    except ValueError:
        return None
    return base.rstrip("/") + "/orchestrate"


def _inference_timeout() -> float | None:
    value = frappe.conf.get("nexmate_inference_timeout", DEFAULT_INFERENCE_TIMEOUT_SECONDS)
    if (type(value) not in (int, float)
            or not 0 < value <= MAX_INFERENCE_TIMEOUT_SECONDS
            or not math.isfinite(value)):
        return None
    return float(value)


def _mode_for_user(user: str) -> str:
    mapping = frappe.conf.get("nexmate_developer_roles", [])
    if (not isinstance(mapping, list)
            or not all(_valid_identity(role) for role in mapping)):
        logger.warning("invalid_developer_roles_config")
        return "employee"
    if not mapping:
        return "employee"
    return "developer" if any(role in mapping for role in frappe.get_roles(user)) else "employee"


def _forward(url: str, key: str, envelope: dict, read_timeout: float) -> dict | str:
    try:
        with requests.Session() as client:
            client.trust_env = False
            with client.post(url, json=envelope, headers={"X-NexMate-Key": key},
                             timeout=(CONNECT_TIMEOUT_SECONDS, read_timeout),
                             allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    return "gateway_upstream_http_error"
                raw = bytearray()
                for chunk in response.iter_content(chunk_size=8192):
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        return "gateway_upstream_response_too_large"
                data = json.loads(raw)
        if not isinstance(data, dict) or not set(RESPONSE_FIELDS) <= data.keys():
            return "gateway_upstream_protocol_error"
        result = {field: data[field] for field in RESPONSE_FIELDS}
        if (not isinstance(result["answer"], str)
                or not isinstance(result["sources"], list)
                or not all(isinstance(source, dict) for source in result["sources"])
                or result["confidence"] not in ("high", "low", "no_match")
                or result["route"] not in ("erpnext", "code", "rag", "smalltalk",
                                           "capability", "clarify", "out_of_scope")
                or result["mode"] != envelope["mode"]
                or result["session_id"] != envelope.get("session_id")
                or not isinstance(result["version_info"], dict)):
            return "gateway_upstream_protocol_error"
        serialized = json.dumps(result).lower()
        if key.lower() in serialized or "x-nexmate-key" in serialized:
            return "gateway_upstream_protocol_error"
        return result
    except requests.Timeout:
        return "gateway_upstream_timeout"
    except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ContentDecodingError,
            ValueError, UnicodeError, RecursionError):
        return "gateway_upstream_protocol_error"
    except requests.RequestException:
        return "gateway_upstream_transport_error"


@frappe.whitelist()
def ask(question: str, session_id: str | None = None) -> dict:
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Authentication required.", frappe.PermissionError)
    form = getattr(frappe, "form_dict", {})
    if set(form) - ALLOWED_FORM_FIELDS:
        logger.warning("unsupported_gateway_fields")
        frappe.throw("unsupported_gateway_fields")
    site = getattr(frappe.local, "site", None)
    if not _valid_identity(user) or not _valid_identity(site):
        frappe.throw("NexMate gateway configuration error.")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
        frappe.throw("Invalid chat question.")
    if session_id is not None and (
            not isinstance(session_id, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id) is None):
        frappe.throw("Invalid session identifier.")
    key = frappe.conf.get("nexmate_service_key")
    url = _inference_url()
    if not _valid_key(key) or url is None:
        frappe.throw("NexMate gateway configuration error.")
    read_timeout = _inference_timeout()
    if read_timeout is None:
        logger.warning("invalid_inference_timeout_config")
        frappe.throw("invalid_inference_timeout_config")
    envelope = {
        "question": question,
        "user": user,
        "site": site,
        "mode": _mode_for_user(user),
        "execution_scope": "chat-only",
    }
    if session_id is not None:
        envelope["session_id"] = session_id
    result = _forward(url, key, envelope, read_timeout)
    if isinstance(result, str):
        logger.warning(result)
        frappe.throw(result)
    return result
