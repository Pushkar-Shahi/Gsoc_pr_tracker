import pytest
import uuid
import httpx
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.database import get_db, init_engine
from app.models.models import User, Organization, Membership, Runner


@pytest.fixture(autouse=True)
async def setup_database():
    engine = await init_engine()
    yield engine


@pytest.mark.asyncio
async def test_dev_github_login_provisions_user_and_workspace():
    """Verifies that POST /auth/github/dev-login creates user, personal org, and session token."""
    username = f"dev_{uuid.uuid4().hex[:8]}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/github/dev-login", json={"username": username})
        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is True
        assert data["username"] == username
        assert data["token"] is not None
        assert data["tenant_id"].startswith("org-")
        assert data["role"] == "owner"


@pytest.mark.asyncio
async def test_list_and_create_organizations():
    """Verifies organization listing, creation, and switching flow."""
    username = f"orguser_{uuid.uuid4().hex[:8]}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Dev login
        login_res = await client.post("/api/v1/auth/github/dev-login", json={"username": username})
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. List organizations
        list_res = await client.get("/api/v1/organizations", headers=headers)
        assert list_res.status_code == 200
        orgs = list_res.json()
        assert len(orgs) >= 1
        assert orgs[0]["is_personal"] is True
        assert orgs[0]["is_active"] is True
        assert orgs[0]["role"] == "owner"

        # 3. Create a new organization
        new_org_name = f"Team-{uuid.uuid4().hex[:6]}"
        create_res = await client.post(
            "/api/v1/organizations",
            headers=headers,
            json={"name": new_org_name}
        )
        assert create_res.status_code == 201
        created_org = create_res.json()
        assert created_org["name"] == new_org_name
        assert created_org["is_personal"] is False
        assert created_org["role"] == "owner"
        new_org_id = created_org["id"]

        # 4. Switch to the newly created organization
        switch_res = await client.post(
            f"/api/v1/organizations/{new_org_id}/switch",
            headers=headers
        )
        assert switch_res.status_code == 200
        switch_data = switch_res.json()
        assert switch_data["organization"]["id"] == new_org_id
        new_token = switch_data["token"]
        assert new_token is not None

        # 5. Verify listing reflects new active organization
        new_headers = {"Authorization": f"Bearer {new_token}"}
        updated_list_res = await client.get("/api/v1/organizations", headers=new_headers)
        assert updated_list_res.status_code == 200
        updated_orgs = updated_list_res.json()
        active_org = next(o for o in updated_orgs if o["id"] == new_org_id)
        assert active_org["is_active"] is True


@pytest.mark.asyncio
async def test_organization_members_lifecycle():
    """Verifies listing and adding members to an organization."""
    username = f"lead_{uuid.uuid4().hex[:8]}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post("/api/v1/auth/github/dev-login", json={"username": username})
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create org
        org_res = await client.post(
            "/api/v1/organizations",
            headers=headers,
            json={"name": f"Guild-{uuid.uuid4().hex[:6]}"}
        )
        org_id = org_res.json()["id"]

        # List members (creator should be owner)
        members_res = await client.get(f"/api/v1/organizations/{org_id}/members", headers=headers)
        assert members_res.status_code == 200
        members = members_res.json()
        assert len(members) == 1
        assert members[0]["username"] == username
        assert members[0]["role"] == "owner"

        # Add a teammate
        teammate = f"teammate_{uuid.uuid4().hex[:6]}"
        add_res = await client.post(
            f"/api/v1/organizations/{org_id}/members",
            headers=headers,
            json={"username_or_email": teammate, "role": "admin"}
        )
        assert add_res.status_code == 201
        added = add_res.json()
        assert added["username"] == teammate
        assert added["role"] == "admin"

        # Verify members list now has 2 members
        updated_members_res = await client.get(f"/api/v1/organizations/{org_id}/members", headers=headers)
        assert updated_members_res.status_code == 200
        assert len(updated_members_res.json()) == 2


@pytest.mark.asyncio
async def test_runner_jobs_poll_accepts_both_get_and_post():
    """Verifies that /api/v1/runners/jobs/poll accepts both GET and POST without returning HTTP 405."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register a runner first to get a valid token
        admin_login = await client.post("/api/v1/auth/login", json={"password": "mwps@1534"})
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["token"]

        reg_res = await client.post(
            "/api/v1/runners/register",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": f"test-runner-{uuid.uuid4().hex[:6]}",
                "os_info": "macOS test",
                "registration_token": admin_token
            }
        )
        assert reg_res.status_code == 201
        runner_token = reg_res.json()["runner_token"]
        runner_headers = {"Authorization": f"Bearer {runner_token}"}

        # 1. GET /jobs/poll
        get_res = await client.get("/api/v1/runners/jobs/poll", headers=runner_headers)
        assert get_res.status_code in (200, 204)

        # 2. POST /jobs/poll (Previously failed with 405 Method Not Allowed!)
        post_res = await client.post("/api/v1/runners/jobs/poll", headers=runner_headers)
        assert post_res.status_code in (200, 204)
        assert post_res.status_code != 405
