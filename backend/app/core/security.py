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
SECRET_KEY: bytes = getattr(settings, "SECRET_KEY", "issuetopr_secure_jwt_secret_mwps_2026").encode("utf-8")
TOKEN_EXPIRY_SECONDS: int = 60 * 60 * 24 * 30  # 30 days session validity

def verify_password(plain_password: str) -> bool:
    """Verifies user input against the required platform password."""
    if not plain_password:
        return False
    # Use hmac.compare_digest to prevent timing attacks
    return hmac.compare_digest(plain_password.strip(), APP_PASSWORD)

def generate_session_token(subject: str = "user") -> str:
    """Generates a tamper-proof cryptographically signed session token."""
    payload: Dict[str, Any] = {
        "sub": subject,
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
        "nonce": secrets.token_hex(8)
    }
    payload_json = json.dumps(payload, separators=(',', ':'))
    b64_payload = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8').rstrip('=')
    
    signature = hmac.new(SECRET_KEY, b64_payload.encode('utf-8'), hashlib.sha256).digest()
    b64_sig = base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')
    
    return f"{b64_payload}.{b64_sig}"

def verify_session_token(token: str) -> bool:
    """Verifies that the session token is untampered and unexpired."""
    if not token or "." not in token:
        return False
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return False
        b64_payload, b64_sig = parts
        
        # Verify signature
        expected_sig = hmac.new(SECRET_KEY, b64_payload.encode('utf-8'), hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(b64_sig + "=" * (-len(b64_sig) % 4))
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return False
            
        # Verify expiry
        payload_bytes = base64.urlsafe_b64decode(b64_payload + "=" * (-len(b64_payload) % 4))
        payload = json.loads(payload_bytes.decode('utf-8'))
        
        if payload.get("exp", 0) < int(time.time()):
            return False
            
        return True
    except Exception:
        return False
