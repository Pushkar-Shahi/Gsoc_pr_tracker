import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from app.core.security import SECRET_KEY

def _get_fernet(key: Optional[bytes] = None) -> Fernet:
    """Derives a Fernet-compatible 32-byte base64 key."""
    if key is not None:
        raw_bytes = key.encode("utf-8") if isinstance(key, str) else key
        fernet_key = base64.urlsafe_b64encode(hashlib.sha256(raw_bytes).digest())
    else:
        fernet_key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY).digest())
    return Fernet(fernet_key)

def encrypt_secret(secret: str, key: Optional[bytes] = None) -> str:
    """Symmetrically encrypts a secret string at rest using AES-256 (Fernet)."""
    if not secret:
        return ""
    f = _get_fernet(key)
    return f.encrypt(secret.encode("utf-8")).decode("utf-8")

def decrypt_secret(encrypted_secret: Optional[str], key: Optional[bytes] = None) -> Optional[str]:
    """Decrypts a secret string at rest. Returns None on corrupted/invalid/empty inputs."""
    if not encrypted_secret:
        return None
    try:
        f = _get_fernet(key)
        return f.decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except Exception:
        return None

def mask_api_key(key: Optional[str]) -> str:
    """Returns a masked preview of an API key (e.g. 'sk-...cdef') without leaking the secret."""
    if not key:
        return ""
    key_str = str(key).strip()
    if not key_str:
        return ""
    if len(key_str) <= 8:
        return "***"
    return f"{key_str[:3]}...{key_str[-4:]}"
