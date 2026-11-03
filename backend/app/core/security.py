import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional, Dict, Any

from app.core.config import settings

# Dedicated password specified by user
APP_PASSWORD: str = getattr(settings, "APP_PASSWORD", "mwps@1534")
SECRET_KEY: bytes = settings.SECRET_KEY.encode("utf-8")
TOKEN_EXPIRY_SECONDS: int = 60 * 60 * 24 * 30  # 30 days session validity

def verify_password(plain_password: str) -> bool:
    """Verifies user input against the required platform password."""
    if not plain_password:
        return False
    # Use hmac.compare_digest to prevent timing attacks
    return hmac.compare_digest(plain_password.strip(), APP_PASSWORD)

def generate_session_token(subject: str = "user", claims: Optional[Dict[str, Any]] = None) -> str:
    """Generates a tamper-proof cryptographically signed session token with optional claims."""
    payload: Dict[str, Any] = {
        "sub": subject,
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
        "nonce": secrets.token_hex(8)
    }
    if claims:
        payload.update(claims)
    payload_json = json.dumps(payload, separators=(',', ':'))
    b64_payload = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8').rstrip('=')
    
    signature = hmac.new(SECRET_KEY, b64_payload.encode('utf-8'), hashlib.sha256).digest()
    b64_sig = base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')
    
    return f"{b64_payload}.{b64_sig}"

def decode_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and cryptographically verifies a session token. Returns payload dict or None."""
    if not token or "." not in token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_payload, b64_sig = parts
        
        # Verify signature
        expected_sig = hmac.new(SECRET_KEY, b64_payload.encode('utf-8'), hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(b64_sig + "=" * (-len(b64_sig) % 4))
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
            
        # Verify expiry
        payload_bytes = base64.urlsafe_b64decode(b64_payload + "=" * (-len(b64_payload) % 4))
        payload = json.loads(payload_bytes.decode('utf-8'))
        
        if payload.get("exp", 0) < int(time.time()):
            return None
            
        return payload
    except Exception:
        return None

def verify_session_token(token: str) -> bool:
    """Verifies that the session token is untampered and unexpired."""
    return decode_session_token(token) is not None

def verify_github_webhook_signature(raw_body: bytes, signature_header: Optional[str], secret: Optional[str] = None) -> bool:
    """Verifies GitHub X-Hub-Signature-256 HMAC-SHA256 signature."""
    import os
    sec = secret or getattr(settings, "GITHUB_WEBHOOK_SECRET", None) or os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not sec or not signature_header or not signature_header.startswith("sha256="):
        return False
    try:
        expected_hash = hmac.new(sec.encode("utf-8") if isinstance(sec, str) else sec, raw_body, hashlib.sha256).hexdigest()
        received_hash = signature_header.split("sha256=", 1)[1].strip()
        return hmac.compare_digest(expected_hash, received_hash)
    except Exception:
        return False
