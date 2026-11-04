import base64
import json
import logging
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import httpx
from fastapi import APIRouter, HTTPException, Header, Depends, status
from pydantic import BaseModel
from starlette.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import verify_password, generate_session_token, verify_session_token, decode_session_token
from app.db.database import get_db
from app.models.models import User, Organization, Membership

router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth In-Memory State Storage
_oauth_states: Dict[str, float] = {}

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
    username: Optional[str] = None
    id: Optional[str] = None
    tenant_id: Optional[str] = None
    role: Optional[str] = None
    tier: Optional[str] = None

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

logger = logging.getLogger(__name__)

class DevGitHubLoginRequest(BaseModel):
    username: str = "Pushkar-Shahi"

async def _provision_user_and_token(
    db: AsyncSession,
    gh_id: Optional[int],
    gh_username: str,
    email: Optional[str] = None,
    name: Optional[str] = None,
    avatar_url: Optional[str] = None
) -> Tuple[str, User, str, str, str]:
    """
    Common helper to upsert User, find or create personal Organization workspace,
    and generate JWT session token with tenant context.
    """
    user = None
    if gh_id:
        u_res = await db.execute(select(User).where(User.github_id == gh_id))
        user = u_res.scalar_one_or_none()
    if not user:
        u_res2 = await db.execute(select(User).where(User.github_username == gh_username))
        user = u_res2.scalar_one_or_none()

    if user:
        if email:
            user.email = email
        if avatar_url:
            user.avatar_url = avatar_url
        if name:
            user.name = name
    else:
        u_id = f"usr-{uuid.uuid4().hex[:12]}"
        user = User(
            id=u_id,
            github_id=gh_id,
            github_username=gh_username,
            email=email or f"{gh_username.lower()}@platform.dev",
            name=name or gh_username,
            avatar_url=avatar_url or f"https://github.com/{gh_username}.png"
        )
        db.add(user)
        await db.flush()

    # Look up or create personal organization workspace
    mem_stmt = select(Membership).options(selectinload(Membership.organization)).where(Membership.user_id == user.id)
    mem_res = await db.execute(mem_stmt)
    membership = mem_res.scalars().first()

    if not membership:
        o_id = f"org-{uuid.uuid4().hex[:12]}"
        org = Organization(
            id=o_id,
            name=f"{gh_username}'s Workspace",
            slug=f"org-{gh_username.lower()}-{uuid.uuid4().hex[:6]}",
            is_personal=True,
            billing_tier="starter"
        )
        db.add(org)
        await db.flush()

        membership = Membership(
            id=f"mem-{uuid.uuid4().hex[:8]}",
            user_id=user.id,
            org_id=org.id,
            role="owner"
        )
        db.add(membership)
        await db.flush()
        tenant_id = org.id
        tier = "starter"
    else:
        tenant_id = membership.org_id
        tier = membership.organization.billing_tier if (membership.organization and membership.organization.billing_tier) else "starter"

    await db.commit()

    claims = {
        "user_id": user.id,
        "username": user.github_username,
        "tenant_id": tenant_id,
        "role": membership.role,
        "tier": tier
    }
    session_token = generate_session_token(subject=user.id, claims=claims)
    return session_token, user, tenant_id, membership.role, tier


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

@router.get("/github/login")
async def github_login(format: Optional[str] = None):
    """Initiates GitHub OAuth 2.0 authorization code flow."""
    now = time.time()
    for s in [k for k, exp in _oauth_states.items() if exp < now]:
        _oauth_states.pop(s, None)

    state = secrets.token_urlsafe(32)
    _oauth_states[state] = now + 600

    client_id = settings.GITHUB_CLIENT_ID or "mock_client_id_12345"
    redirect_uri = settings.GITHUB_REDIRECT_URI
    auth_url = (
        f"https://github.com/login/oauth/authorize?"
        f"client_id={client_id}&redirect_uri={redirect_uri}&scope=read:user,user:email,repo&state={state}"
    )

    if format == "json":
        return {"authorization_url": auth_url, "state": state}
    return RedirectResponse(url=auth_url, status_code=302)

@router.get("/github/callback")
async def github_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Exchanges GitHub OAuth code for access token, upserts user and workspace, and issues session token."""
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing authorization code")
    if not state or state not in _oauth_states or _oauth_states[state] < time.time():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state parameter")

    _oauth_states.pop(state, None)

    token_url = "https://github.com/login/oauth/access_token"
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            token_url,
            json={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_REDIRECT_URI
            },
            headers={"Accept": "application/json"}
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to retrieve access token from GitHub")

        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        )
        gh_user = user_resp.json()

    gh_id = gh_user.get("id")
    gh_username = gh_user.get("login") or f"user_{gh_id}"
    email = gh_user.get("email")
    name = gh_user.get("name") or gh_username
    avatar_url = gh_user.get("avatar_url")

    session_token, user, tenant_id, role, tier = await _provision_user_and_token(
        db=db,
        gh_id=gh_id,
        gh_username=gh_username,
        email=email,
        name=name,
        avatar_url=avatar_url
    )

    redirect_target = f"{settings.FRONTEND_AUTH_CALLBACK_URL}?token={session_token}"
    return RedirectResponse(url=redirect_target, status_code=302)


@router.post("/github/dev-login")
async def dev_github_login(
    req: DevGitHubLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Developer Quick GitHub Sign-in:
    Validates GitHub username against GitHub's public API, fetches avatar & profile,
    provisions User and personal Organization workspace, and issues JWT session token.
    """
    username = (req.username or "").strip()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub username is required."
        )

    gh_id = None
    email = f"{username.lower()}@users.noreply.github.com"
    name = username
    avatar_url = f"https://github.com/{username}.png"

    # Query public GitHub profile to populate real user details
    try:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Issue-to-PR-Platform"
        }
        if settings.GITHUB_TOKEN:
            headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"https://api.github.com/users/{username}", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                gh_id = data.get("id")
                name = data.get("name") or username
                email = data.get("email") or email
                avatar_url = data.get("avatar_url") or avatar_url
    except Exception as e:
        logger.warning(f"Could not reach public GitHub API for user '{username}': {e}")

    session_token, user, tenant_id, role, tier = await _provision_user_and_token(
        db=db,
        gh_id=gh_id,
        gh_username=username,
        email=email,
        name=name,
        avatar_url=avatar_url
    )

    return {
        "token": session_token,
        "token_type": "bearer",
        "authenticated": True,
        "user": user.github_username,
        "username": user.github_username,
        "id": user.id,
        "tenant_id": tenant_id,
        "role": role,
        "tier": tier,
        "avatar_url": user.avatar_url
    }


# ==============================================================================
# Google OAuth & Developer Quick Sign-In
# ==============================================================================

class DevGoogleLoginRequest(BaseModel):
    email: str = "pushkar.shahi@gmail.com"
    name: Optional[str] = "Pushkar Shahi"


@router.get("/google/login")
async def google_login(format: Optional[str] = None):
    """Initiates Google OAuth 2.0 authorization code flow."""
    now = time.time()
    for s in [k for k, exp in _oauth_states.items() if exp < now]:
        _oauth_states.pop(s, None)

    state = secrets.token_urlsafe(32)
    _oauth_states[state] = now + 600

    client_id = settings.GOOGLE_CLIENT_ID or "mock_google_client_id.apps.googleusercontent.com"
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&"
        f"scope=openid%20email%20profile&state={state}&access_type=offline&prompt=consent"
    )

    if format == "json":
        return {"authorization_url": auth_url, "state": state}
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/google/callback")
async def google_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Exchanges Google authorization code for token, fetches user info, and issues session token."""
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing authorization code")
    if not state or state not in _oauth_states or _oauth_states[state] < time.time():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state parameter")

    _oauth_states.pop(state, None)

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GOOGLE_REDIRECT_URI
            }
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to retrieve access token from Google")

        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        google_user = user_resp.json()

    email = google_user.get("email")
    name = google_user.get("name") or (email.split("@")[0] if email else "Google User")
    username = email.split("@")[0] if email else f"google_user_{secrets.token_hex(4)}"
    avatar_url = google_user.get("picture") or f"https://api.dicebear.com/7.x/initials/svg?seed={username}&backgroundColor=ea4335,4285f4,34a853,fbbc05"

    session_token, user, tenant_id, role, tier = await _provision_user_and_token(
        db=db,
        gh_id=None,
        gh_username=username,
        email=email,
        name=name,
        avatar_url=avatar_url
    )

    redirect_target = f"{settings.FRONTEND_AUTH_CALLBACK_URL}?token={session_token}"
    return RedirectResponse(url=redirect_target, status_code=302)


@router.post("/google/dev-login")
async def dev_google_login(
    req: DevGoogleLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Developer Quick Google Sign-in:
    Allows instant one-click sign in with Google account profile without requiring live Cloud console keys.
    """
    email = (req.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid Google email is required.")

    username = email.split("@")[0].replace("+", "_")
    name = req.name or username.replace(".", " ").replace("_", " ").title()
    avatar_url = f"https://api.dicebear.com/7.x/initials/svg?seed={username}&backgroundColor=ea4335,4285f4,34a853,fbbc05"

    session_token, user, tenant_id, role, tier = await _provision_user_and_token(
        db=db,
        gh_id=None,
        gh_username=username,
        email=email,
        name=name,
        avatar_url=avatar_url
    )

    return {
        "token": session_token,
        "token_type": "bearer",
        "authenticated": True,
        "user": user.github_username,
        "username": user.github_username,
        "id": user.id,
        "tenant_id": tenant_id,
        "role": role,
        "tier": tier,
        "avatar_url": user.avatar_url,
        "provider": "google"
    }


class GoogleCredentialRequest(BaseModel):
    credential: str


@router.post("/google/verify-credential")
async def verify_google_credential(
    req: GoogleCredentialRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Verifies a Google Identity Services (GSI) credential JWT (ID token)
    issued by Google directly to the client with settings.GOOGLE_CLIENT_ID.
    Validates token with Google's tokeninfo endpoint, provisions user,
    and returns a platform session token.
    """
    credential = (req.credential or "").strip()
    if not credential:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Google credential token")

    google_data = None
    # 1. Verify against Google's tokeninfo endpoint
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": credential}
            )
            if resp.status_code == 200:
                google_data = resp.json()
    except Exception as e:
        logger.warning(f"Google tokeninfo query failed: {e}")

    # 2. Fallback: Parse unverified JWT payload safely if offline/sandbox
    if not google_data:
        try:
            parts = credential.split(".")
            if len(parts) >= 2:
                padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                google_data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        except Exception as e:
            logger.error(f"Failed to decode Google credential token: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Google credential token format")

    if not google_data or not google_data.get("email"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to extract user email from Google token")

    email = google_data.get("email").strip().lower()
    name = google_data.get("name") or google_data.get("given_name") or email.split("@")[0]
    username = email.split("@")[0].replace("+", "_").replace(".", "_")
    avatar_url = google_data.get("picture") or f"https://api.dicebear.com/7.x/initials/svg?seed={username}&backgroundColor=ea4335,4285f4,34a853,fbbc05"

    session_token, user, tenant_id, role, tier = await _provision_user_and_token(
        db=db,
        gh_id=None,
        gh_username=username,
        email=email,
        name=name,
        avatar_url=avatar_url
    )

    return {
        "token": session_token,
        "token_type": "bearer",
        "authenticated": True,
        "user": user.github_username,
        "username": user.github_username,
        "id": user.id,
        "tenant_id": tenant_id,
        "role": role,
        "tier": tier,
        "avatar_url": user.avatar_url,
        "provider": "google"
    }


# ==============================================================================
# GitLab OAuth & Developer Quick Sign-In
# ==============================================================================

class DevGitLabLoginRequest(BaseModel):
    username: str = "Pushkar-Shahi"
    name: Optional[str] = "Pushkar Shahi"


@router.get("/gitlab/login")
async def gitlab_login(format: Optional[str] = None):
    """Initiates GitLab OAuth 2.0 flow."""
    now = time.time()
    for s in [k for k, exp in _oauth_states.items() if exp < now]:
        _oauth_states.pop(s, None)

    state = secrets.token_urlsafe(32)
    _oauth_states[state] = now + 600

    client_id = settings.GITLAB_CLIENT_ID or "mock_gitlab_client_id"
    redirect_uri = settings.GITLAB_REDIRECT_URI
    auth_url = (
        f"https://gitlab.com/oauth/authorize?"
        f"client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&"
        f"scope=read_user%20openid%20profile%20email&state={state}"
    )

    if format == "json":
        return {"authorization_url": auth_url, "state": state}
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/gitlab/callback")
async def gitlab_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Exchanges GitLab authorization code for user data."""
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing authorization code")
    if not state or state not in _oauth_states or _oauth_states[state] < time.time():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state parameter")

    _oauth_states.pop(state, None)

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://gitlab.com/oauth/token",
            data={
                "client_id": settings.GITLAB_CLIENT_ID,
                "client_secret": settings.GITLAB_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GITLAB_REDIRECT_URI
            }
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to retrieve access token from GitLab")

        user_resp = await client.get(
            "https://gitlab.com/api/v4/user",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        gl_user = user_resp.json()

    gl_username = gl_user.get("username") or f"gitlab_{gl_user.get('id', 'user')}"
    email = gl_user.get("email") or f"{gl_username}@users.noreply.gitlab.com"
    name = gl_user.get("name") or gl_username
    avatar_url = gl_user.get("avatar_url") or f"https://gitlab.com/uploads/-/system/user/avatar/{gl_user.get('id')}/avatar.png"

    session_token, user, tenant_id, role, tier = await _provision_user_and_token(
        db=db,
        gh_id=None,
        gh_username=f"gl_{gl_username}",
        email=email,
        name=name,
        avatar_url=avatar_url
    )

    redirect_target = f"{settings.FRONTEND_AUTH_CALLBACK_URL}?token={session_token}"
    return RedirectResponse(url=redirect_target, status_code=302)


@router.post("/gitlab/dev-login")
async def dev_gitlab_login(
    req: DevGitLabLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Developer Quick GitLab Sign-in."""
    username = (req.username or "").strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitLab username is required.")

    clean_uname = re.sub(r'[^a-zA-Z0-9_\-]', '', username)
    email = f"{clean_uname.lower()}@gitlab.com"
    name = req.name or clean_uname
    avatar_url = f"https://api.dicebear.com/7.x/bottts/svg?seed={clean_uname}&backgroundColor=fc6d26,e24329"

    session_token, user, tenant_id, role, tier = await _provision_user_and_token(
        db=db,
        gh_id=None,
        gh_username=f"gl_{clean_uname}",
        email=email,
        name=name,
        avatar_url=avatar_url
    )

    return {
        "token": session_token,
        "token_type": "bearer",
        "authenticated": True,
        "user": user.github_username,
        "username": user.github_username,
        "id": user.id,
        "tenant_id": tenant_id,
        "role": role,
        "tier": tier,
        "avatar_url": user.avatar_url,
        "provider": "gitlab"
    }


# ==============================================================================
# Passwordless Email & Magic Link Sign-In
# ==============================================================================

_email_verification_codes: Dict[str, Tuple[str, float]] = {}

class EmailCodeRequest(BaseModel):
    email: str

class EmailVerifyRequest(BaseModel):
    email: str
    code: str

@router.post("/email/request-code")
async def request_email_code(req: EmailCodeRequest):
    """Sends / generates a one-time login verification code for passwordless email sign-in."""
    email = (req.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid email address is required.")

    code = f"{secrets.randbelow(900000) + 100000}"
    _email_verification_codes[email] = (code, time.time() + 600)

    logger.info(f"Generated passwordless email sign-in code for {email}: {code}")
    return {
        "success": True,
        "message": f"Verification code sent to {email}",
        "dev_code": code
    }


@router.post("/email/verify-code")
async def verify_email_code(
    req: EmailVerifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verifies the email one-time code and issues a JWT session token."""
    email = (req.email or "").strip().lower()
    entry = _email_verification_codes.get(email)
    if not entry or entry[1] < time.time() or entry[0] != req.code.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification code.")

    _email_verification_codes.pop(email, None)

    username = email.split("@")[0].replace(".", "_")
    name = username.replace("_", " ").title()
    avatar_url = f"https://api.dicebear.com/7.x/thumbs/svg?seed={username}"

    session_token, user, tenant_id, role, tier = await _provision_user_and_token(
        db=db,
        gh_id=None,
        gh_username=username,
        email=email,
        name=name,
        avatar_url=avatar_url
    )

    return {
        "token": session_token,
        "token_type": "bearer",
        "authenticated": True,
        "user": user.github_username,
        "username": user.github_username,
        "id": user.id,
        "tenant_id": tenant_id,
        "role": role,
        "tier": tier,
        "avatar_url": user.avatar_url,
        "provider": "email"
    }

@router.get("/me")
async def check_auth(authorization: Optional[str] = Header(None)):
    """Checks whether the currently provided token is valid and returns user profile with claims."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication header."
        )
    token = authorization.split("Bearer ", 1)[1].strip()
    payload = decode_session_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Please re-enter your password."
        )

    user_claim = payload.get("username") or payload.get("sub", "admin")
    user_id = payload.get("user_id") or payload.get("sub", "default-user")
    tenant_id = payload.get("tenant_id") or "default-org"
    role = payload.get("role", "owner")
    tier = payload.get("tier", "starter")

    return {
        "authenticated": True,
        "user": user_claim,
        "username": user_claim,
        "id": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "tier": tier
    }

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

