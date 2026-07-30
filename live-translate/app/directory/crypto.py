"""Encryption boundary for voluntary directory contact details."""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class DirectoryCryptoError(RuntimeError):
    pass


def _fernet(key: str | None = None) -> Fernet:
    raw = (key or settings.directory_contact_key).strip()
    if not raw:
        raise DirectoryCryptoError("DIRECTORY_CONTACT_KEY is not configured")
    try:
        return Fernet(raw.encode())
    except (TypeError, ValueError) as exc:
        raise DirectoryCryptoError("DIRECTORY_CONTACT_KEY is invalid") from exc


def encrypt_contacts(value: dict[str, str], *, key: str | None = None) -> str:
    cleaned = {str(k): str(v).strip() for k, v in value.items() if str(v).strip()}
    payload = json.dumps(cleaned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _fernet(key).encrypt(payload.encode("utf-8")).decode("ascii")


def decrypt_contacts(ciphertext: str, *, key: str | None = None) -> dict[str, str]:
    try:
        raw = _fernet(key).decrypt(ciphertext.encode("ascii"))
        value = json.loads(raw.decode("utf-8"))
    except (InvalidToken, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise DirectoryCryptoError("Contact data cannot be decrypted") from exc
    if not isinstance(value, dict):
        raise DirectoryCryptoError("Contact data is invalid")
    return {str(k): str(v) for k, v in value.items()}
