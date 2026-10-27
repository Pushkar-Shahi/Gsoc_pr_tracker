import uuid
import random
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from app.db.database import get_session_factory
from app.models.models import Task, Issue, Repository
from app.services.background_worker import sync_task_pr_status
from app.services.pr_publisher import PRPublisher
from app.services.github_client import GitHubClient

@pytest.mark.asyncio
async def test_pr_status_sync_handles_changes_requested():
    session_factory = await get_session_factory()
    suffix = uuid.uuid4().hex[:6]
    async with session_factory() as db:
        repo = Repository(
            owner=f"org-{suffix}",
            name=f"proj-{suffix}",
            full_name=f"org-{suffix}/proj-{suffix}",
            html_url=f"https://github.com/org-{suffix}/proj-{suffix}",
            default_branch="main"
        )
        db.add(repo)
        await db.flush()

        issue = Issue(
            repository_id=repo.id,
            github_id=random.randint(10000000, 99999999),
            issue_number=50,
            title="PR Review Test Issue",
            html_url=f"https://github.com/org-{suffix}/proj-{suffix}/issues/50"
        )
        db.add(issue)
        await db.flush()

        task = Task(
            issue_id=issue.id,
            workflow_state="PR_CREATED",
            pr_number=12,
            pr_url=f"https://github.com/org-{suffix}/proj-{suffix}/pull/12"
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id

        # Re-fetch with relationships
        stmt = select(Task).where(Task.id == task_id)
        r = await db.execute(stmt)
        task = r.scalar_one()

        mock_gh = AsyncMock(spec=GitHubClient)
        mock_gh.get_pull_request.return_value = {
            "state": "open",
            "merged": False,
            "head": {"sha": "abc123commit"}
        }
        mock_gh.get_commit_check_runs.return_value = {
            "status": "success",
            "runs": [{"name": "pytest", "conclusion": "success"}]
        }
        mock_gh.get_pull_request_reviews.return_value = [
            {
                "id": 101,
                "state": "CHANGES_REQUESTED",
                "user": {"login": "lead-maintainer"},
                "body": "Please add unit test coverage for edge case when parameter is empty.",
                "submitted_at": "2026-10-23T12:00:00Z"
            }
        ]

        result = await sync_task_pr_status(task, db, mock_gh)

        assert result["synced"] is True
        assert result["pr_review_status"] == "CHANGES_REQUESTED"
        assert result["pr_ci_status"] == "success"
        # Verify it transitions back to COLLABORATIVE_WORK
        assert result["workflow_state"] == "COLLABORATIVE_WORK"
        assert task.workflow_state == "COLLABORATIVE_WORK"
        assert len(task.pr_review_comments) == 1
        assert task.pr_review_comments[0]["author"] == "lead-maintainer"

@pytest.mark.asyncio
async def test_pr_status_sync_handles_merged_pr():
    session_factory = await get_session_factory()
    suffix = uuid.uuid4().hex[:6]
    async with session_factory() as db:
        repo = Repository(
            owner=f"org2-{suffix}",
            name=f"proj2-{suffix}",
            full_name=f"org2-{suffix}/proj2-{suffix}",
            html_url=f"https://github.com/org2-{suffix}/proj2-{suffix}",
            default_branch="main"
        )
        db.add(repo)
        await db.flush()

        issue = Issue(
            repository_id=repo.id,
            github_id=random.randint(10000000, 99999999),
            issue_number=51,
            title="Merged PR Issue",
            html_url=f"https://github.com/org2-{suffix}/proj2-{suffix}/issues/51"
        )
        db.add(issue)
        await db.flush()

        task = Task(
            issue_id=issue.id,
            workflow_state="IN_REVIEW",
            pr_number=15,
            pr_url=f"https://github.com/org2-{suffix}/proj2-{suffix}/pull/15"
        )
        db.add(task)
        await db.commit()

        mock_gh = AsyncMock(spec=GitHubClient)
        mock_gh.get_pull_request.return_value = {
            "state": "closed",
            "merged": True,
            "merged_at": "2026-10-23T12:30:00Z",
            "head": {"sha": "mergedsha"}
        }
        mock_gh.get_commit_check_runs.return_value = {"status": "success", "runs": []}
        mock_gh.get_pull_request_reviews.return_value = []

        result = await sync_task_pr_status(task, db, mock_gh)

        assert result["pr_merged"] is True
        assert result["workflow_state"] == "MERGED_OR_CLOSED"
        assert task.workflow_state == "MERGED_OR_CLOSED"

@pytest.mark.asyncio
async def test_pr_publisher_detects_duplicate_pr_and_blocks():
    mock_gh = AsyncMock(spec=GitHubClient)
    mock_gh.get_issue.return_value = {"state": "open", "assignees": []}
    # Simulate an existing PR already addressing issue #42
    mock_gh.find_existing_pull_request.return_value = {
        "number": 99,
        "title": "Fixes #42 - pre-existing duplicate submission",
        "html_url": "https://github.com/upstream/repo/pull/99"
    }

    publisher = PRPublisher(github_client=mock_gh)
    res = await publisher.publish_pull_request(
        worktree_path="/tmp",  # path exists
        owner="upstream",
        repo="repo",
        issue_number=42,
        issue_title="Test Issue",
        branch_name="fix/issue-42-test"
    )

    assert res["success"] is False
    assert "duplicate pull request detected" in res["error"].lower()
    assert "99" in res["error"]
