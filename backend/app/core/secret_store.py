from __future__ import annotations

import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if normalized.startswith(_PREFIX):
        return normalized
    token = _fernet().encrypt(normalized.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_secret(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if not normalized.startswith(_PREFIX):
        return normalized
    try:
        return _fernet().decrypt(normalized[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def mask_secret(value: Optional[str]) -> Optional[str]:
    plain = decrypt_secret(value)
    if not plain:
        return None
    if len(plain) <= 8:
        return "*" * len(plain)
    return f"{plain[:4]}...{plain[-4:]}"
