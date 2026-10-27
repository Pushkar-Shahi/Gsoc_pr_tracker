import uuid
import random
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from app.db.database import get_session_factory
from app.models.models import Task, Issue, Repository
from app.services.background_worker import reconcile_tasks_on_startup

@pytest.mark.asyncio
async def test_startup_reconciliation_resets_interrupted_validation():
    session_factory = await get_session_factory()
    suffix = uuid.uuid4().hex[:6]
    async with session_factory() as db:
        # Create a repo and issue
        repo = Repository(
            owner=f"owner-{suffix}",
            name=f"repo-{suffix}",
            full_name=f"owner-{suffix}/repo-{suffix}",
            html_url=f"https://github.com/owner-{suffix}/repo-{suffix}",
            default_branch="main",
            primary_language="Python",
            stars_count=100
        )
        db.add(repo)
        await db.flush()

        issue = Issue(
            repository_id=repo.id,
            github_id=random.randint(10000000, 99999999),
            issue_number=101,
            title="Interrupted test issue",
            html_url=f"https://github.com/owner-{suffix}/repo-{suffix}/issues/101",
            state="open"
        )
        db.add(issue)
        await db.flush()

        # Task interrupted in VALIDATING state
        task = Task(
            issue_id=issue.id,
            workflow_state="VALIDATING",
            worktree_path="/nonexistent/worktree/path"
        )
        db.add(task)
        await db.commit()
        task_id = task.id

    # Mock GitHubClient so it reports issue as open
    with patch("app.services.background_worker.GitHubClient") as mock_gh_cls:
        mock_gh = AsyncMock()
        mock_gh.get_issue.return_value = {"state": "open", "assignees": []}
        mock_gh_cls.return_value = mock_gh

        await reconcile_tasks_on_startup(session_factory)

    async with session_factory() as db:
        res = await db.execute(select(Task).where(Task.id == task_id))
        reconciled_task = res.scalar_one()

        assert reconciled_task.workflow_state == "READY_FOR_VALIDATION"
        assert "interrupted" in (reconciled_task.blocked_reason or "").lower()

@pytest.mark.asyncio
async def test_startup_reconciliation_blocks_task_if_upstream_closed():
    session_factory = await get_session_factory()
    suffix = uuid.uuid4().hex[:6]
    async with session_factory() as db:
        repo = Repository(
            owner=f"owner-{suffix}",
            name=f"closed-repo-{suffix}",
            full_name=f"owner-{suffix}/closed-repo-{suffix}",
            html_url=f"https://github.com/owner-{suffix}/closed-repo-{suffix}",
            default_branch="main",
            primary_language="Python",
            stars_count=100
        )
        db.add(repo)
        await db.flush()

        issue = Issue(
            repository_id=repo.id,
            github_id=random.randint(10000000, 99999999),
            issue_number=102,
            title="Closed issue",
            html_url=f"https://github.com/owner-{suffix}/closed-repo-{suffix}/issues/102",
            state="open"
        )
        db.add(issue)
        await db.flush()

        task = Task(
            issue_id=issue.id,
            workflow_state="COLLABORATIVE_WORK"
        )
        db.add(task)
        await db.commit()
        task_id = task.id

    with patch("app.services.background_worker.GitHubClient") as mock_gh_cls:
        mock_gh = AsyncMock()
        mock_gh.get_issue.return_value = {"state": "closed", "assignees": []}
        mock_gh_cls.return_value = mock_gh

        await reconcile_tasks_on_startup(session_factory)

    async with session_factory() as db:
        res = await db.execute(select(Task).where(Task.id == task_id))
        reconciled_task = res.scalar_one()

        assert reconciled_task.workflow_state == "BLOCKED"
        assert "closed on github" in (reconciled_task.blocked_reason or "").lower()

@pytest.mark.asyncio
async def test_inbox_reconcile_with_purge():
    from app.services.background_worker import reconcile_inbox_issues_upstream
    session_factory = await get_session_factory()
    suffix = uuid.uuid4().hex[:6]
    async with session_factory() as db:
        repo = Repository(
            owner=f"owner-{suffix}",
            name=f"purge-repo-{suffix}",
            full_name=f"owner-{suffix}/purge-repo-{suffix}",
            html_url=f"https://github.com/owner-{suffix}/purge-repo-{suffix}",
            default_branch="main",
            primary_language="Python",
            stars_count=50
        )
        db.add(repo)
        await db.flush()

        issue = Issue(
            repository_id=repo.id,
            github_id=random.randint(10000000, 99999999),
            issue_number=103,
            title="Stale unattached issue",
            html_url=f"https://github.com/owner-{suffix}/purge-repo-{suffix}/issues/103",
            state="open",
            is_eligible=True
        )
        db.add(issue)
        await db.commit()
        issue_id = issue.id

    with patch("app.services.background_worker.GitHubClient") as mock_gh_cls:
        mock_gh = AsyncMock()
        mock_gh.get_issue.return_value = {"state": "closed", "assignees": []}
        mock_gh_cls.return_value = mock_gh

        result = await reconcile_inbox_issues_upstream(session_factory, max_issues=None, purge=True)
        assert result["reconciled_closed"] >= 1
        assert result["purged"] >= 1

    async with session_factory() as db:
        res = await db.execute(select(Issue).where(Issue.id == issue_id))
        purged_issue = res.scalar_one_or_none()
        assert purged_issue is None

@pytest.mark.asyncio
async def test_select_issue_rejects_closed_upstream():
    from fastapi import HTTPException
    from app.api.v1.tasks import select_issue
    from app.schemas.schemas import TaskCreate
    session_factory = await get_session_factory()
    suffix = uuid.uuid4().hex[:6]
    async with session_factory() as db:
        repo = Repository(
            owner=f"owner-{suffix}",
            name=f"select-repo-{suffix}",
            full_name=f"owner-{suffix}/select-repo-{suffix}",
            html_url=f"https://github.com/owner-{suffix}/select-repo-{suffix}",
            default_branch="main",
            primary_language="Python",
            stars_count=50
        )
        db.add(repo)
        await db.flush()

        issue = Issue(
            repository_id=repo.id,
            github_id=random.randint(10000000, 99999999),
            issue_number=104,
            title="Recently closed issue",
            html_url=f"https://github.com/owner-{suffix}/select-repo-{suffix}/issues/104",
            state="open",
            is_eligible=True
        )
        db.add(issue)
        await db.commit()
        issue_id = issue.id

        with patch("app.api.v1.tasks.get_github_client") as mock_get_gh:
            mock_gh = AsyncMock()
            mock_gh.get_issue.return_value = {"state": "closed", "assignees": []}
            mock_get_gh.return_value = mock_gh

            with pytest.raises(HTTPException) as exc_info:
                await select_issue(TaskCreate(issue_id=issue_id), db=db)

            assert exc_info.value.status_code == 409
            assert "closed or assigned upstream" in exc_info.value.detail.lower()

        # Check that DB was updated
        res = await db.execute(select(Issue).where(Issue.id == issue_id))
        updated_issue = res.scalar_one()
        assert updated_issue.state == "closed"
        assert updated_issue.is_eligible is False

