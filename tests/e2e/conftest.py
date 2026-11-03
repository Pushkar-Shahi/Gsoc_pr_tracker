"""E2E Test Configuration and Fixtures for Phase 1 (Multi-Tenancy & GitHub App Foundation).

Provides:
- Database session and table initialization fixtures
- HMAC-SHA256 signature generator (create_signed_webhook_payload)
- Mock GitHub OAuth 2.0 endpoints fixture (mock_github_oauth)
- Mock GitHub API client responses (mock_github_api)
- Test tenant, user, organization, and membership factory
- Session token generation with custom claims
- Async HTTP client fixture (client)
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# 1. Ensure backend directory and project root are in sys.path
backend_path = Path(__file__).resolve().parent.parent.parent / "backend"
project_root = Path(__file__).resolve().parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 2. Configure isolated test database
test_db_url = f"postgresql+asyncpg://{os.getenv('USER', 'shahi')}@localhost:5432/issuetopr_test"
os.environ["DATABASE_URL"] = test_db_url

from app.core.config import settings
settings.DATABASE_URL = test_db_url

from app.core.security import SECRET_KEY, generate_session_token, verify_session_token
from app.db.database import create_tables, get_session_factory, init_engine
from app.main import app

# Constants for test suite
TEST_WEBHOOK_SECRET = "test_github_webhook_secret_hmac_2026"
TEST_ENCRYPTION_SECRET = "issuetopr_secure_jwt_secret_mwps_2026"


# ---------------------------------------------------------------------------
# Cryptographic & Webhook Payload Generators
# ---------------------------------------------------------------------------

def create_signed_webhook_payload(
    event_type: str,
    payload_data: Dict[str, Any],
    secret: str = TEST_WEBHOOK_SECRET
) -> Tuple[Dict[str, str], bytes]:
    """Serializes a dictionary payload and computes a valid GitHub X-Hub-Signature-256 header."""
    payload_bytes = json.dumps(payload_data, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    headers = {
        "X-GitHub-Event": event_type,
        "X-Hub-Signature-256": f"sha256={signature}",
        "X-GitHub-Delivery": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    return headers, payload_bytes


def make_session_token(
    subject: str = "user",
    claims: Optional[Dict[str, Any]] = None,
    secret: bytes = SECRET_KEY,
    expires_in: int = 86400
) -> str:
    """Creates a tamper-proof HMAC-SHA256 session token with claims."""
    payload: Dict[str, Any] = {
        "sub": subject,
        "exp": int(time.time()) + expires_in,
        "nonce": secrets.token_hex(8)
    }
    if claims:
        payload.update(claims)
        
    payload_json = json.dumps(payload, separators=(',', ':'))
    b64_payload = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8').rstrip('=')
    signature = hmac.new(secret, b64_payload.encode('utf-8'), hashlib.sha256).digest()
    b64_sig = base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')
    return f"{b64_payload}.{b64_sig}"


# ---------------------------------------------------------------------------
# Database & Client Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
async def init_e2e_db():
    """Initializes async engine and ensures table creation."""
    await init_engine()
    await create_tables()
    yield


@pytest.fixture
async def db_session():
    """Provides an isolated AsyncSession for database inspection within a test."""
    session_factory = await get_session_factory()
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client():
    """Provides an unauthenticated AsyncClient for hitting FastAPI endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Mock GitHub OAuth 2.0 & API Fixtures
# ---------------------------------------------------------------------------

MOCK_GITHUB_USER = {
    "id": 99887766,
    "login": "bounty-hunter-pro",
    "name": "Bounty Hunter Pro",
    "email": "hunter@platform.dev",
    "avatar_url": "https://avatars.githubusercontent.com/u/99887766",
}

MOCK_GITHUB_EMAILS = [
    {"email": "hunter@platform.dev", "primary": True, "verified": True},
    {"email": "hunter@users.noreply.github.com", "primary": False, "verified": True}
]

MOCK_ACCESS_TOKEN_RESPONSE = {
    "access_token": "gho_mock_oauth_access_token_super_secret_12345",
    "token_type": "bearer",
    "scope": "read:user,user:email,repo"
}


@pytest.fixture
def mock_github_oauth():
    """Mocks external HTTP calls during GitHub OAuth code exchange and user retrieval."""
    from unittest.mock import MagicMock
    _orig_get = AsyncClient.get
    _orig_post = AsyncClient.post

    async def mock_post_router(self, url, *args, **kwargs):
        url_str = str(url)
        if "github.com" in url_str:
            post_resp = MagicMock()
            post_resp.status_code = 200
            post_resp.json.return_value = MOCK_ACCESS_TOKEN_RESPONSE
            return post_resp
        return await _orig_post(self, url, *args, **kwargs)

    async def mock_get_router(self, url, *args, **kwargs):
        url_str = str(url)
        if "github.com" in url_str:
            get_resp = MagicMock()
            get_resp.status_code = 200
            if "/user/emails" in url_str:
                get_resp.json.return_value = MOCK_GITHUB_EMAILS
            elif "/user" in url_str:
                get_resp.json.return_value = MOCK_GITHUB_USER
            else:
                get_resp.json.return_value = {}
            return get_resp
        return await _orig_get(self, url, *args, **kwargs)

    with patch.object(AsyncClient, "post", new=mock_post_router) as mock_post, \
         patch.object(AsyncClient, "get", new=mock_get_router) as mock_get:
        yield {
            "post": mock_post,
            "get": mock_get,
            "user": MOCK_GITHUB_USER,
            "access_token": MOCK_ACCESS_TOKEN_RESPONSE["access_token"]
        }


@pytest.fixture
def mock_github_client():
    """Mocks the GitHubClient class to prevent any live external calls during tests."""
    mock_gh = AsyncMock()
    mock_gh.get_issue.return_value = {
        "state": "open",
        "assignees": [],
        "title": "Mock Issue for Testing",
        "body": "Reproduction details",
        "labels": [{"name": "bug"}],
        "comments": 0
    }
    mock_gh.list_issue_comments.return_value = []
    mock_gh.get_contributing_guidelines.return_value = None
    mock_gh.get_repository.return_value = {
        "id": 1234567,
        "name": "test-repo",
        "full_name": "test-owner/test-repo",
        "default_branch": "main",
        "archived": False,
        "disabled": False
    }
    mock_gh.create_pull_request.return_value = {
        "number": 101,
        "html_url": "https://github.com/test-owner/test-repo/pull/101",
        "state": "open"
    }

    with patch("app.api.v1.tasks.get_github_client", return_value=mock_gh), \
         patch("app.api.v1.tracker.get_github_client", return_value=mock_gh):
        yield mock_gh


# ---------------------------------------------------------------------------
# Test Tenant & Identity Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tenant_factory():
    """Factory fixture returning a helper function to construct test tenant profiles & tokens."""
    def _create_tenant(
        user_id: Optional[str] = None,
        username: str = "test-user",
        org_id: Optional[str] = None,
        org_slug: str = "test-org",
        role: str = "owner",
        tier: str = "pro"
    ) -> Dict[str, Any]:
        u_id = user_id or f"usr-{uuid.uuid4().hex[:12]}"
        o_id = org_id or f"org-{uuid.uuid4().hex[:12]}"
        claims = {
            "user_id": u_id,
            "username": username,
            "tenant_id": o_id,
            "role": role,
            "tier": tier
        }
        token = make_session_token(subject=u_id, claims=claims)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": o_id
        }
        return {
            "user_id": u_id,
            "username": username,
            "org_id": o_id,
            "org_slug": org_slug,
            "role": role,
            "tier": tier,
            "token": token,
            "headers": headers,
            "claims": claims
        }
    return _create_tenant
