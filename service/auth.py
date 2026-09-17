import hmac
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
        return False
    if not getattr(request.state, "service_authenticated", False):
        raise HTTPException(status_code=401, detail="gateway_credential_required")
    if not envelope_fields.union({"mode"}) <= supplied:
        raise HTTPException(status_code=422, detail="invalid_gateway_envelope")
    if (not valid_identity(payload["user"]) or payload["user"] == "Guest"
            or not valid_identity(payload["site"])
            or payload["mode"] not in ("developer", "employee")
            or payload["execution_scope"] != "chat-only"):
        raise HTTPException(status_code=422, detail="invalid_gateway_envelope")
    if not valid_identity(config.NEXMATE_FRAPPE_SITE):
        raise HTTPException(status_code=503, detail="invalid_frappe_site_config")
    if payload["site"] != config.NEXMATE_FRAPPE_SITE:
        raise HTTPException(status_code=403, detail="gateway_site_mismatch")
    return True
