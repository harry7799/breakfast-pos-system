from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from app.config import settings

PBKDF2_ROUNDS = 210_000


def _b64_url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64_url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ROUNDS,
    )
    return f"{PBKDF2_ROUNDS}${salt}${digest.hex()}"


MAX_PBKDF2_ROUNDS = 1_000_000


def verify_password(password: str, password_hash: str) -> bool:
    try:
        rounds_str, salt, digest_hex = password_hash.split("$", 2)
        rounds = int(rounds_str)
    except ValueError:
        return False
    if rounds <= 0 or rounds > MAX_PBKDF2_ROUNDS:
        return False
    computed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        rounds,
    )
    return hmac.compare_digest(computed.hex(), digest_hex)


def create_access_token(*, user_id: int, username: str, role: str) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expire_minutes)
    payload = {
        "uid": user_id,
        "username": username,
        "role": role,
        "exp": int(expires_at.timestamp()),
    }
    payload_segment = _b64_url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    )
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        payload_segment.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature_segment = _b64_url_encode(signature)
    return f"{payload_segment}.{signature_segment}", expires_at


def verify_access_token(token: str) -> dict | None:
    try:
        payload_segment, signature_segment = token.split(".", 1)
    except ValueError:
        return None

    expected_sig = hmac.new(
        settings.secret_key.encode("utf-8"),
        payload_segment.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    actual_sig = _b64_url_decode(signature_segment)
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None

    try:
        payload = json.loads(_b64_url_decode(payload_segment))
    except (json.JSONDecodeError, ValueError):
        return None

    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        return None
    return payload

