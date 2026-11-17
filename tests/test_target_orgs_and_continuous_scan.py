import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.database import get_session_factory
from app.models.models import Repository, Issue, Task
from app.services.discovery_service import DiscoveryService
from app.core.security import generate_session_token


@pytest.mark.asyncio
async def test_continuous_scan_purges_unselected_issues_and_preserves_selected():
    """Verify scanning purges old unselected issues but keeps issues where Select Issue was clicked."""
    session_factory = await get_session_factory()
    async with session_factory() as db:
        unique_suffix = uuid.uuid4().hex[:6]
        # Create a test repository with unique full_name
        repo = Repository(
            owner=f"testorg-{unique_suffix}",
            name="testrepo",
            full_name=f"testorg-{unique_suffix}/testrepo",
            html_url=f"https://github.com/testorg-{unique_suffix}/testrepo",
            default_branch="main",
            primary_language="Python",
            license_spdx="Apache-2.0",
            stars_count=1000,
            is_gsoc=True,
            gsoc_org_name="TestOrg"
        )
        db.add(repo)
        await db.flush()

        # Create an unselected issue
        unselected_issue = Issue(
            repository_id=repo.id,
            github_id=int(uuid.uuid4().int % 900_000_000),
            issue_number=1001,
            title="Unselected old issue that should be cleared",
            body="Should be purged on next scan",
            html_url=f"https://github.com/{repo.full_name}/issues/1001",
            state="open",
            is_eligible=True,
        )
        db.add(unselected_issue)

        # Create a selected issue (has an associated Task)
        selected_issue = Issue(
            repository_id=repo.id,
            github_id=int(uuid.uuid4().int % 900_000_000),
            issue_number=1002,
            title="Selected issue that MUST be preserved",
            body="User clicked select issue",
            html_url=f"https://github.com/{repo.full_name}/issues/1002",
            state="open",
            is_eligible=True,
        )
        db.add(selected_issue)
        await db.flush()

        task = Task(
            issue_id=selected_issue.id,
            workflow_state="SELECTED"
        )
        db.add(task)
        await db.commit()

        # Run discovery scan with mocked gh client returning 1 fresh candidate
        gh = MagicMock()
        gh.rate_limit_remaining = 5000
        gh.rate_limit_limit = 5000
        gh.get_repo_issues = AsyncMock(return_value=[])
        fresh_gh_id = int(uuid.uuid4().int % 900_000_000)
        gh.search_issues = AsyncMock(return_value={
            "items": [
                {
                    "id": fresh_gh_id,
                    "number": 555,
                    "title": "Fresh scanned issue",
                    "body": "Newly found issue",
                    "html_url": f"https://github.com/{repo.full_name}/issues/555",
                    "repository_url": f"https://api.github.com/repos/{repo.full_name}",
                    "state": "open",
                    "user": {"login": "dev"},
                    "labels": [],
                    "assignees": [],
                    "comments": 0
                }
            ]
        })
        gh.get_repository = AsyncMock(return_value={
            "stargazers_count": 1000,
            "license": {"spdx_id": "Apache-2.0"},
            "archived": False,
            "default_branch": "main"
        })
        gh.get_issue_linked_prs = AsyncMock(return_value=[])

        service = DiscoveryService(db=db, github_client=gh)
        await service.run_discovery_sync(force_refresh=True, page_limit=1)

        # Verify unselected issue was purged
        res1 = await db.execute(select(Issue).where(Issue.id == unselected_issue.id))
        assert res1.scalar_one_or_none() is None

        # Verify selected issue was preserved
        res2 = await db.execute(select(Issue).where(Issue.id == selected_issue.id))
        preserved = res2.scalar_one_or_none()
        assert preserved is not None
        assert preserved.issue_number == 1002


@pytest.mark.asyncio
async def test_target_orgs_and_continuous_cron_status():
    """Verify cron status returns 24/7 interval and target orgs list."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = generate_session_token(subject="user-standard", claims={"role": "member", "tier": "starter"})
        headers = {"Authorization": f"Bearer {token}"}

        # Check cron status with auth header
        resp = await client.get("/api/v1/discovery/cron-status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["interval_seconds"] == 300
        assert "Zulip" in data["target_orgs"]
        assert "Learning Equality" in data["target_orgs"]
        assert "Rocket.Chat" in data["target_orgs"]
        assert "CircuitVerse.org" in data["target_orgs"]
        assert "Wikimedia Foundation" in data["target_orgs"]
        assert "NumFOCUS" not in data["target_orgs"]

        # Check organizations endpoint
        orgs_resp = await client.get("/api/v1/issues/organizations", headers=headers)
        assert orgs_resp.status_code == 200
        orgs_data = orgs_resp.json()
        org_ids = [o["id"] for o in orgs_data["organizations"]]
        assert "zulip" in org_ids
        assert "learningequality" in org_ids
        assert "rocketchat" in org_ids
        assert "circuitverse" in org_ids
        assert "wikimedia" in org_ids
        assert "numfocus" not in org_ids
        assert "kornia" not in org_ids
