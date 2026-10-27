import pytest
from app.services.policy_inspector import PolicyInspector

class MockGitHubClient:
    def __init__(self, contributing_text="", repo_license="MIT", is_archived=False):
        self.contributing_text = contributing_text
        self.repo_license = repo_license
        self.is_archived = is_archived

    async def get_repository(self, owner, repo):
        return {
            "archived": self.is_archived,
            "license": {"spdx_id": self.repo_license, "name": self.repo_license} if self.repo_license else None
        }

    async def get_file_content(self, owner, repo, path):
        return self.contributing_text

@pytest.mark.asyncio
async def test_policy_requires_assignment_when_explicitly_stated():
    mock_gh = MockGitHubClient(contributing_text="Please comment to claim an issue before starting work.")
    inspector = PolicyInspector(github_client=mock_gh)

    res = await inspector.inspect_repository_policy(
        owner="org",
        repo="repo",
        issue_number=123,
        issue_body="Feature request",
        issue_labels=[],
        issue_assignees=[]
    )

    assert res["workflow_state"] == "ASSIGNMENT_REQUEST_REQUIRED"
    assert res["assignment_required"] is True
    assert res["draft_comment"] is not None
    assert "#123" in res["draft_comment"]

@pytest.mark.asyncio
async def test_policy_ready_to_work_when_no_assignment_rules():
    mock_gh = MockGitHubClient(contributing_text="Standard open source project. Feel free to submit PRs.")
    inspector = PolicyInspector(github_client=mock_gh)

    res = await inspector.inspect_repository_policy(
        owner="org",
        repo="repo",
        issue_number=456,
        issue_body="Bug report",
        issue_labels=[],
        issue_assignees=[]
    )

    assert res["workflow_state"] == "READY_TO_WORK"
    assert res["assignment_required"] is False
    assert res["draft_comment"] is None

@pytest.mark.asyncio
async def test_policy_blocked_when_already_assigned():
    mock_gh = MockGitHubClient()
    inspector = PolicyInspector(github_client=mock_gh)

    res = await inspector.inspect_repository_policy(
        owner="org",
        repo="repo",
        issue_number=789,
        issue_body="Another issue",
        issue_labels=[],
        issue_assignees=[{"login": "existing_developer"}]
    )

    assert res["workflow_state"] == "BLOCKED"
    assert any("already assigned" in e for e in res["evidence"])
