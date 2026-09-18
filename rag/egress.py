"""Deny-by-default provider egress boundary (M4 provider-egress-policy).

Every provider call — generation, corrective retries, NLU, condensation,
embeddings, evaluation judges — passes `guarded_call`, which permits
transmission only under an explicit (data_class, provider, purpose) grant
and otherwise refuses loudly. There is no silent downgrade, reroute, or
provider switching: an unavailable granted provider fails safely.

Secrets (configured keys, 64-hex credential shapes, transport headers) are
excluded from every payload regardless of ordinary content approval.

Grants are explicit and auditable: `set_grants()` replaces the table (used
by tests and, with user approval, by operators); production grants remain a
DECISIONS.md approval, never inferred from configuration.
"""

import os
import re
from typing import Any, Callable

import config

Hex64_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_SECRET_ENV_NAMES = ("NEXMATE_SERVICE_KEY", "ANTHROPIC_API_KEY",
                     "OPENAI_API_KEY")


class EgressDenied(RuntimeError):
    """A provider transmission was refused by deny-by-default policy."""


# (data_class, provider, purpose) triples explicitly permitted.
# None = uninitialized: check() installs default_generation_grants()
# lazily so tests (set_grants) and operators fully control the table,
# while ordinary startup keeps today's configured behavior working.
_grants: frozenset | None = None


def set_grants(grants) -> None:
    """Replace the grant table (tests / explicitly approved operators)."""
    global _grants
    _grants = frozenset(tuple(g) for g in grants)


def get_grants() -> frozenset:
    global _grants
    if _grants is None:
        _grants = default_generation_grants()
    return _grants


def default_generation_provider() -> str:
    """Provider selected by configuration (empty when unconfigured)."""
    return os.environ.get("GENERATION_PROVIDER", "")


def default_generation_grants() -> frozenset:
    """Baseline grants for the configured generation provider + local tools.

    Configuration selects; policy enforces. Anything not listed here (any
    other provider, any unlisted purpose) is denied until explicitly
    granted via set_grants(). Local embeddings and the local eval judge
    are always granted: they never leave the box. Production cloud grants
    remain a user approval recorded in DECISIONS.md.
    """
    provider = default_generation_provider()
    grants = {
        ("embedding", config.EGRESS_LOCAL_PROVIDER, "embed"),
        ("embedding", config.EGRESS_LOCAL_PROVIDER, "evaluate"),
        ("eval", "ollama", "evaluate"),
    }
    if provider:
        for data_class in ("prompt", "history", "company_content",
                           "live_result"):
            for purpose in ("answer", "retry", "nlu", "condense"):
                grants.add((data_class, provider, purpose))
    return frozenset(grants)


def _secret_values() -> list[str]:
    values = []
    for name in _SECRET_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            values.append(value)
    return values


def assert_no_secrets(text: str) -> None:
    """Fail loud if payload text carries secret material."""
    if not isinstance(text, str) or not text:
        return
    lowered = text.lower()
    for secret in _secret_values():
        if secret and secret.lower() in lowered:
            raise EgressDenied("payload contains secret material")
    if "x-nexmate-key" in lowered:
        raise EgressDenied("payload contains transport credential")
    if Hex64_RE.search(text):
        raise EgressDenied("payload contains credential-shaped material")


def check(data_class: str, provider: str, purpose: str,
          payload_text: str = "") -> None:
    """Permit or refuse a provider transmission (raises EgressDenied)."""
    global _grants
    if _grants is None:
        _grants = default_generation_grants()
    if data_class not in config.EGRESS_DATA_CLASSES:
        raise EgressDenied(f"unknown data class {data_class!r}")
    if purpose not in config.EGRESS_PURPOSES:
        raise EgressDenied(f"unknown purpose {purpose!r}")
    assert_no_secrets(payload_text)
    if (data_class, provider, purpose) not in _grants:
        raise EgressDenied(
            f"no grant for {data_class}/{provider}/{purpose}")


def guarded_call(data_class: str, provider: str, purpose: str, fn: Callable,
                 *args: Any, payload_text: str = "", **kwargs: Any) -> Any:
    """Run fn only when the transmission is granted; otherwise refuse."""
    check(data_class, provider, purpose, payload_text)
    return fn(*args, **kwargs)


def contains_marker(text: str) -> bool:
    """Synthetic sensitive-data markers for the test harness (never real)."""
    return isinstance(text, str) and config.EGRESS_MARKER_PREFIX in text
