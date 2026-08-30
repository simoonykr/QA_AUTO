import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import Settings


COOKIE_NAME = "tracepilot_demo_session"


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def validate_demo_auth_config(settings: Settings) -> None:
    if not settings.demo_auth_enabled:
        return
    if not settings.demo_auth_username or not settings.demo_auth_password:
        raise RuntimeError("Demo authentication credentials are not configured")
    if len(settings.demo_session_secret) < 32:
        raise RuntimeError("DEMO_SESSION_SECRET must contain at least 32 characters")
    if settings.demo_cookie_samesite == "none" and not settings.demo_cookie_secure:
        raise RuntimeError("DEMO_COOKIE_SECURE must be true when DEMO_COOKIE_SAMESITE is none")
    if settings.app_env not in {"local", "test"} and not settings.demo_cookie_secure:
        raise RuntimeError("DEMO_COOKIE_SECURE must be true outside local and test environments")


def credentials_match(username: str, password: str, settings: Settings) -> bool:
    return hmac.compare_digest(username, settings.demo_auth_username) and hmac.compare_digest(
        password, settings.demo_auth_password
    )


def create_session(settings: Settings) -> tuple[str, int]:
    ttl_seconds = max(1, settings.demo_session_ttl_hours) * 3600
    payload = {
        "sub": settings.demo_auth_username,
        "role": "OWNER",
        "approvalStatus": "APPROVED",
        "exp": int(time.time()) + ttl_seconds,
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _encode(hmac.new(settings.demo_session_secret.encode(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}", ttl_seconds


def verify_session(token: str | None, settings: Settings) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        encoded, supplied_signature = token.split(".", maxsplit=1)
        expected_signature = _encode(
            hmac.new(settings.demo_session_secret.encode(), encoded.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_decode(encoded))
        if payload.get("exp", 0) <= int(time.time()):
            return None
        if payload.get("sub") != settings.demo_auth_username:
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
