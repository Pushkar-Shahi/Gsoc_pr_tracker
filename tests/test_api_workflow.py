import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app, lifespan
from app.core.security import generate_session_token

@pytest.mark.asyncio
async def test_full_api_workflow():
    token = generate_session_token()
    headers = {"Authorization": f"Bearer {token}"}
    from app.db.database import get_session_factory
    from app.models.models import Repository, Issue
    from sqlalchemy import select

    import uuid
    unique_suffix = uuid.uuid4().hex[:8]
    test_iss_id = f"test-iss-workflow-{unique_suffix}"
    session_factory = await get_session_factory()
    async with session_factory() as session:
        r_stmt = select(Repository).where(Repository.id == "test-psf-repo")
        r_res = await session.execute(r_stmt)
        if not r_res.scalar_one_or_none():
            repo = Repository(
                id="test-psf-repo",
                owner="psf",
                name="requests",
                full_name="psf/requests",
                html_url="https://github.com/psf/requests",
                default_branch="main",
                is_fork=False,
                is_archived=False,
                is_gsoc=True,
                gsoc_org_name="Python Software Foundation"
            )
            session.add(repo)
        iss = Issue(
            id=test_iss_id,
            repository_id="test-psf-repo",
            github_id=int(unique_suffix, 16) % 10000000 + 1000,
            issue_number=int(unique_suffix, 16) % 900000 + 10000,
            title="Test Issue in PSF",
            body="Sample bug report",
            html_url=f"https://github.com/psf/requests/issues/{int(unique_suffix, 16) % 900000 + 10000}",
            state="open",
            is_eligible=True,
            ranking_score=90
        )
        session.add(iss)
        await session.commit()

    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
            # 1. Health check
            r = await ac.get("/api/health")
            assert r.status_code == 200

            # 2. Issues listing
            issues_res = await ac.get("/api/v1/issues")
            assert issues_res.status_code == 200
            data = issues_res.json()
            assert len(data["items"]) > 0

            # 3. Select issue
            from unittest.mock import AsyncMock, patch
            mock_gh = AsyncMock()
            mock_gh.get_issue.return_value = {"state": "open", "assignees": [], "title": "Test Issue", "body": "Sample", "labels": []}
            mock_gh.list_issue_comments.return_value = []
            mock_gh.get_contributing_guidelines.return_value = None
            with patch("app.api.v1.tasks.get_github_client", return_value=mock_gh):
                select_res = await ac.post("/api/v1/tasks/select", json={"issue_id": test_iss_id})
                assert select_res.status_code == 200
                task = select_res.json()
                task_id = task["id"]
                assert task["workflow_state"] in ("READY_TO_WORK", "ASSIGNMENT_REQUEST_REQUIRED", "POLICY_REVIEW_REQUIRED", "BLOCKED")

            # 4. Settings read & update
            sett_res = await ac.get("/api/v1/settings")
            assert sett_res.status_code == 200

            update_res = await ac.put("/api/v1/settings", json={"auto_publish_pr": False})
            assert update_res.status_code == 200
            assert update_res.json()["auto_publish_pr"] is False

            # 5. Audit logs verify recording
            audit_res = await ac.get("/api/v1/audit-logs")
            assert audit_res.status_code == 200
            assert len(audit_res.json()) > 0
