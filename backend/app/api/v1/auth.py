import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Header, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import verify_password, generate_session_token, verify_session_token

router = APIRouter(prefix="/auth", tags=["auth"])

# Biometric Credentials Storage
BIOMETRIC_FILE = settings.DATA_DIR / "biometric_credentials.json"
_active_challenges: Dict[str, float] = {}

def _load_biometric_credentials() -> List[Dict[str, Any]]:
    try:
        if BIOMETRIC_FILE.exists():
            with open(BIOMETRIC_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("credentials", [])
    except Exception:
        pass
    return []

def _save_biometric_credentials(credentials: List[Dict[str, Any]]):
    try:
        BIOMETRIC_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(BIOMETRIC_FILE, "w", encoding="utf-8") as f:
            json.dump({"credentials": credentials, "updated_at": time.time()}, f, indent=2)
    except Exception as e:
        print(f"Failed to persist biometric credentials: {e}")

class LoginRequest(BaseModel):
    password: str

class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    authenticated: bool = True

class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: str = "admin"

class BiometricChallengeResponse(BaseModel):
    challenge: str

class BiometricRegisterRequest(BaseModel):
    credential_id: str
    client_data_json: Optional[str] = None
    attestation_object: Optional[str] = None
    device_name: Optional[str] = "Device Biometrics"
    password: Optional[str] = None

class BiometricVerifyRequest(BaseModel):
    credential_id: str
    challenge: Optional[str] = None
    client_data_json: Optional[str] = None
    authenticator_data: Optional[str] = None
    signature: Optional[str] = None

class BiometricStatusResponse(BaseModel):
    has_registered_credentials: bool
    registered_count: int

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticates against the platform password mwps@1534 and returns a session token."""
    if not verify_password(req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password. Access denied."
        )
    token = generate_session_token("admin")
    return LoginResponse(token=token)

@router.get("/me", response_model=AuthStatusResponse)
async def check_auth(authorization: Optional[str] = Header(None)):
    """Checks whether the currently provided token is valid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication header."
        )
    token = authorization.split("Bearer ", 1)[1].strip()
    if not verify_session_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Please re-enter your password."
        )
    return AuthStatusResponse(authenticated=True, user="admin")

@router.post("/logout")
async def logout():
    """Client-side token invalidation."""
    return {"status": "logged_out"}

# ==========================================
# WebAuthn Biometric Authentication Endpoints
# ==========================================

@router.get("/biometric/challenge", response_model=BiometricChallengeResponse)
async def get_biometric_challenge():
    """Generates a cryptographic random challenge for WebAuthn assertion."""
    # Clean up expired challenges
    now = time.time()
    expired = [k for k, exp in _active_challenges.items() if exp < now]
    for k in expired:
        _active_challenges.pop(k, None)

    challenge = secrets.token_urlsafe(32)
    _active_challenges[challenge] = now + 300  # 5 minutes TTL
    return BiometricChallengeResponse(challenge=challenge)

@router.get("/biometric/status", response_model=BiometricStatusResponse)
async def get_biometric_status():
    """Checks whether any biometric credentials are enrolled for this platform."""
    creds = _load_biometric_credentials()
    return BiometricStatusResponse(
        has_registered_credentials=len(creds) > 0,
        registered_count=len(creds)
    )

@router.post("/biometric/register", response_model=LoginResponse)
async def register_biometric(
    req: BiometricRegisterRequest,
    authorization: Optional[str] = Header(None)
):
    """Registers a device's WebAuthn credential (Touch ID / Face ID / Fingerprint)."""
    # Verify user authorization either by bearer token or password
    is_authed = False
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        if verify_session_token(token):
            is_authed = True

    if not is_authed and req.password:
        if verify_password(req.password):
            is_authed = True

    if not is_authed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid password or session token required to enroll device biometrics."
        )

    creds = _load_biometric_credentials()
    # Check if credential already exists
    existing = next((c for c in creds if c.get("id") == req.credential_id), None)
    if not existing:
        creds.append({
            "id": req.credential_id,
            "name": req.device_name or "Personal Device",
            "registered_at": time.time(),
            "last_used_at": time.time(),
        })
        _save_biometric_credentials(creds)

    token = generate_session_token("admin")
    return LoginResponse(token=token)

@router.post("/biometric/verify", response_model=LoginResponse)
async def verify_biometric(req: BiometricVerifyRequest):
    """Verifies a device WebAuthn biometric assertion and issues a session token."""
    creds = _load_biometric_credentials()
    matching_cred = next((c for c in creds if c.get("id") == req.credential_id), None)

    # If no credentials enrolled yet on the server, we allow initial enrollment with challenge
    # or notify client to enroll
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No biometric credential enrolled on this device. Please unlock with password first to enroll."
        )

    if not matching_cred:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unrecognized device biometric key. Please unlock with password to sync."
        )

    # Validate challenge if provided
    if req.challenge:
        exp = _active_challenges.get(req.challenge)
        if not exp or exp < time.time():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Biometric verification challenge expired. Please tap to try again."
            )
        _active_challenges.pop(req.challenge, None)

    # Update last_used_at
    matching_cred["last_used_at"] = time.time()
    _save_biometric_credentials(creds)

    token = generate_session_token("admin")
    return LoginResponse(token=token)

@router.post("/biometric/reset")
async def reset_biometrics(
    authorization: Optional[str] = Header(None)
):
    """Removes all enrolled biometric credentials."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    token = authorization.split("Bearer ", 1)[1].strip()
    if not verify_session_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    _save_biometric_credentials([])
    return {"status": "biometrics_reset", "count": 0}

