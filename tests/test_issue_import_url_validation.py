import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from httpx import ASGITransport, AsyncClient

project_root = Path(__file__).resolve().parent.parent
backend_path = project_root / "backend"
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.main import app
from app.core.security import generate_session_token

@pytest.mark.asyncio
async def test_issue_import_validation_error_message():
    token = generate_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.background_worker.reconcile_tasks_on_startup", new_callable=AsyncMock), \
         patch("app.services.background_worker.BackgroundWorkerService.start", return_value=None):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test invalid URL format
            resp = await client.post(
                "/api/v1/issues/import",
                headers=headers,
                json={"url": "not-a-valid-github-url"}
            )
            assert resp.status_code == 400
            data = resp.json()
            assert data["detail"] == "Please enter a valid GitHub issue URL (e.g. https://github.com/numpy/numpy/issues)"

@pytest.mark.asyncio
async def test_issue_import_repo_issues_tab_url():
    token = generate_session_token()
    headers = {"Authorization": f"Bearer {token}"}

    mock_repo = {
        "name": "numpy",
        "owner": {"login": "numpy"},
        "full_name": "numpy/numpy",
        "html_url": "https://github.com/numpy/numpy",
        "default_branch": "main",
        "stargazers_count": 25000,
        "open_issues_count": 120,
        "license": {"spdx_id": "BSD-3-Clause", "name": "BSD 3-Clause"},
        "archived": False,
        "private": False,
        "language": "Python"
    }
    mock_issues = [
        {
            "id": 999901,
            "number": 1234,
            "title": "Fix memory leak in ndarray slicing",
            "body": "When slicing arrays with strides, memory is not freed immediately.",
            "state": "open",
            "user": {"login": "tester"},
            "assignees": [],
            "labels": [{"name": "bug", "color": "d73a4a"}],
            "comments": 2,
            "created_at": "2026-03-01T12:00:00Z",
            "html_url": "https://github.com/numpy/numpy/issues/1234"
        }
    ]

    with patch("app.services.background_worker.reconcile_tasks_on_startup", new_callable=AsyncMock), \
         patch("app.services.background_worker.BackgroundWorkerService.start", return_value=None), \
         patch("app.api.v1.issues.GitHubClient.get_repository", new=AsyncMock(return_value=mock_repo)), \
         patch("app.api.v1.issues.GitHubClient.get_repo_issues", new=AsyncMock(return_value=mock_issues)), \
         patch("app.api.v1.issues.GitHubClient.get_issue", new=AsyncMock(return_value=mock_issues[0])), \
         patch("app.api.v1.issues.GitHubClient.get_issue_linked_prs", new=AsyncMock(return_value=[])), \
         patch("app.services.policy_inspector.PolicyInspector.inspect_repository_policy", new=AsyncMock(return_value={
             "workflow_state": "ready_to_work",
             "assignment_required": False,
             "evidence": "Policy allows self-assignment"
         })):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test repo issue tab URL: https://github.com/numpy/numpy/issues
            resp = await client.post(
                "/api/v1/issues/import",
                headers=headers,
                json={"url": "https://github.com/numpy/numpy/issues"}
            )
            assert resp.status_code == 200, resp.text
            res_data = resp.json()
            assert "issue" in res_data
            assert res_data["issue"]["issue_number"] == 1234
            assert res_data["issue"]["repository"]["full_name"] == "numpy/numpy"
            assert "conditions_checked" in res_data
            assert res_data["meets_all_conditions"] is True
