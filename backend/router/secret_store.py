"""Encrypt-at-rest storage for customer provider credentials.

BYOM on a RouteWise key means keeping somebody else's provider key so every
client that holds the RouteWise key gets the same model. That is the one secret
RouteWise stores on a customer's behalf, so it is encrypted with Fernet before
it reaches the database and is never returned by any endpoint -- reads expose a
masked hint and a boolean instead.

The encryption key comes from ``BYOM_ENCRYPTION_KEY``. If that is unset we
derive one from ``SUPABASE_SERVICE_KEY`` so the deployed instance works without
another secret to rotate. If neither is configured, writes are refused rather
than falling back to plaintext.

Deriving from the Supabase service key means rotating that key makes already
stored provider keys undecryptable. They are then ignored (and logged) instead
of being sent to the wrong provider, and the owner can simply re-save them.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from router.config import BYOM_ENCRYPTION_KEY, SUPABASE_SERVICE_KEY

log = logging.getLogger("routewise")


def _fernet() -> Fernet | None:
    if BYOM_ENCRYPTION_KEY:
        try:
            return Fernet(BYOM_ENCRYPTION_KEY.encode())
        except (ValueError, TypeError):
            log.error("BYOM_ENCRYPTION_KEY is not a valid Fernet key; BYOM storage disabled")
            return None
    if SUPABASE_SERVICE_KEY:
        digest = hashlib.sha256(f"routewise-byom:{SUPABASE_SERVICE_KEY}".encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    return None


def available() -> bool:
    """False when the server has no secret to encrypt with."""
    return _fernet() is not None


def encrypt(raw: str) -> str | None:
    f = _fernet()
    if f is None:
        return None
    return f.encrypt(raw.encode()).decode()


def decrypt(token: str) -> str | None:
    """None when unset, rotated or corrupt -- the caller must not guess."""
    f = _fernet()
    if f is None or not token:
        return None
    try:
        return f.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        log.warning("stored BYOM credential could not be decrypted (encryption key changed?)")
        return None


def mask(raw: str | None) -> str:
    """A hint the owner can recognise: ``sk-...f93a`` and never the middle."""
    raw = raw or ""
    if not raw:
        return ""
    if len(raw) <= 8:
        return "…"
    return f"{raw[:3]}…{raw[-4:]}"
