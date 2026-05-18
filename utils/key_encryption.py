"""
Per-user API key encryption using Fernet with HKDF-derived keys.

Each user gets a unique Fernet key derived from the master SETTINGS_SECRET
via HKDF(master, info=user_id). Knowing one user's encrypted blob does not
help decrypt another user's keys.

Generate SETTINGS_SECRET once:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_APP_SALT = b"pragna-api-keys-v1"


def _master_bytes() -> bytes:
    secret = os.environ.get("SETTINGS_SECRET", "")
    if not secret:
        raise RuntimeError(
            "SETTINGS_SECRET env var is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    padded = secret + "=" * (-len(secret) % 4)
    return base64.urlsafe_b64decode(padded)


def _derive_fernet(user_id: str) -> Fernet:
    derived = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=_APP_SALT,
        info=user_id.encode(),
    ).derive(_master_bytes())
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(value: str, user_id: str) -> str:
    return _derive_fernet(user_id).encrypt(value.encode()).decode()


def decrypt(token: str, user_id: str) -> str:
    return _derive_fernet(user_id).decrypt(token.encode()).decode()


def get_key(provider: str) -> str:
    """Return decrypted API key for the current request's user (via ContextVar)."""
    from utils.user_context import get_user_key
    return get_user_key(provider)


def get_anthropic_mode() -> str:
    from utils.user_context import get_anthropic_mode as _m
    return _m()
