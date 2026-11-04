import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.security import generate_session_token


@pytest.mark.asyncio
async def test_multi_provider_sign_in_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Google Dev Sign-In
        g_resp = await client.post(
            "/api/v1/auth/google/dev-login",
            json={"email": "contributor.test@gmail.com", "name": "Contributor Test"}
        )
        assert g_resp.status_code == 200
        g_data = g_resp.json()
        assert g_data["authenticated"] is True
        assert g_data["provider"] == "google"
        assert "token" in g_data
        token = g_data["token"]

        # 2. GitLab Dev Sign-In
        gl_resp = await client.post(
            "/api/v1/auth/gitlab/dev-login",
            json={"username": "gitlab_tester", "name": "GitLab Tester"}
        )
        assert gl_resp.status_code == 200
        gl_data = gl_resp.json()
        assert gl_data["authenticated"] is True
        assert gl_data["provider"] == "gitlab"
        assert "token" in gl_data

        # 3. Passwordless Email Sign-In
        req_resp = await client.post(
            "/api/v1/auth/email/request-code",
            json={"email": "magic.tester@company.io"}
        )
        assert req_resp.status_code == 200
        req_data = req_resp.json()
        assert req_data["success"] is True
        code = req_data["dev_code"]
        assert len(code) == 6

        verify_resp = await client.post(
            "/api/v1/auth/email/verify-code",
            json={"email": "magic.tester@company.io", "code": code}
        )
        assert verify_resp.status_code == 200
        verify_data = verify_resp.json()
        assert verify_data["authenticated"] is True
        assert verify_data["provider"] == "email"


@pytest.mark.asyncio
async def test_dynamic_organizations_list():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Use valid token
        token = generate_session_token(subject="admin-test", claims={"role": "owner", "tier": "pro"})
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/issues/organizations", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_orgs" in data
        assert "organizations" in data
        assert data["total_orgs"] >= 4

        # Check default 4 organizations exist
        org_ids = [org["id"] for org in data["organizations"]]
        assert "numfocus" in org_ids
        assert "psf" in org_ids
        assert "deepchem" in org_ids
        assert "kornia" in org_ids


@pytest.mark.asyncio
async def test_add_organization_by_url():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = generate_session_token(subject="admin-test", claims={"role": "owner", "tier": "pro"})
        headers = {"Authorization": f"Bearer {token}"}

        # Add organization by issue tab URL
        resp = await client.post(
            "/api/v1/issues/add-org-by-url",
            headers=headers,
            json={"url": "https://github.com/pallets/click/issues", "custom_name": "Click CLI"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["owner"] == "pallets"
        assert data["repo"] == "click"
        assert "issues_imported" in data

