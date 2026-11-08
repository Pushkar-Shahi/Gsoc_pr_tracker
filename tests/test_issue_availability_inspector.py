import pytest
from app.services.availability_inspector import AvailabilityInspector
from app.services.github_client import GitHubClient

def test_detect_maintainer_reservation_kornia_6640():
    """Verifies that kornia#6640 is correctly detected as maintainer-reserved."""
    title = "XFeat* starts matches at the top-left pixel of the 8 px cell: moving it 3 px in takes HPatches AUC@3 from 0.27 to 0.43"
    body = (
        "**This issue is reserved for a maintainer implementation.** It is not open for contribution: "
        "the fix would move the matches `match_xfeat_star` returns and depart from the reference's origin, "
        "so it has to be judged on final matching accuracy, including relative pose, with the maintainers' evaluation. "
        "A PR against this issue from outside the maintainer team will be closed and pointed here."
    )
    is_reserved, reason = AvailabilityInspector.detect_maintainer_reservation(title, body)
    assert is_reserved is True
    assert "reserved for a maintainer" in reason.lower() or "maintainer implementation" in reason.lower()

def test_detect_maintainer_reservation_normal_issue():
    """Verifies that normal bug reports are not flagged as reserved."""
    title = "Fix typo in documentation"
    body = "In section 2, there is a spelling mistake on word 'transform'."
    is_reserved, reason = AvailabilityInspector.detect_maintainer_reservation(title, body)
    assert is_reserved is False
    assert reason is None

def test_classify_issue_availability_states():
    """Verifies that availability states prioritize RESERVED -> ASSIGNED -> PR_OPEN -> AVAILABLE."""
    # 1. Reserved takes precedence
    status_reserved = AvailabilityInspector.classify_issue_availability(
        assignees=[{"login": "testuser"}],
        is_reserved=True,
        linked_prs=[{"number": 123, "state": "open"}]
    )
    assert status_reserved == "RESERVED"

    # 2. Assigned
    status_assigned = AvailabilityInspector.classify_issue_availability(
        assignees=[{"login": "testuser"}],
        is_reserved=False,
        linked_prs=[{"number": 123, "state": "open"}]
    )
    assert status_assigned == "ASSIGNED"

    # 3. Open PR pending review (e.g. Debcode2006 on kornia#6621)
    status_pr_open = AvailabilityInspector.classify_issue_availability(
        assignees=[],
        is_reserved=False,
        linked_prs=[{"number": 6628, "title": "fix: accept background tensor", "state": "open", "author": "Debcode2006"}]
    )
    assert status_pr_open == "PR_OPEN"

    # 4. Clean available issue
    status_clean = AvailabilityInspector.classify_issue_availability(
        assignees=[],
        is_reserved=False,
        linked_prs=[]
    )
    assert status_clean == "AVAILABLE"

    # 5. Closed PRs don't block an issue
    status_closed_pr = AvailabilityInspector.classify_issue_availability(
        assignees=[],
        is_reserved=False,
        linked_prs=[{"number": 500, "state": "closed"}]
    )
    assert status_closed_pr == "AVAILABLE"

@pytest.mark.asyncio
async def test_github_client_get_issue_linked_prs_from_timeline(monkeypatch):
    """Verifies that GitHubClient accurately extracts cross-referenced open PRs."""
    mock_timeline_events = [
        {"event": "subscribed", "id": 1},
        {
            "event": "cross-referenced",
            "source": {
                "issue": {
                    "number": 6628,
                    "title": "fix(color): accept background tensor",
                    "html_url": "https://github.com/kornia/kornia/pull/6628",
                    "state": "open",
                    "pull_request": {"url": "https://api.github.com/repos/kornia/kornia/pulls/6628"},
                    "user": {"login": "Debcode2006", "avatar_url": "https://github.com/Debcode2006.png"}
                }
            }
        },
        {
            "event": "cross-referenced",
            "source": {
                "issue": {
                    "number": 6500,
                    "title": "old closed pr",
                    "state": "closed",
                    "pull_request": {"url": "https://api.github.com/repos/kornia/kornia/pulls/6500"},
                    "user": {"login": "olduser"}
                }
            }
        }
    ]

    import httpx
    async def mock_get(self, url, headers=None, params=None):
        class MockResp:
            status_code = 200
            headers = {}
            def json(self):
                if "timeline" in url:
                    return mock_timeline_events
                return {"items": []}
        return MockResp()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = GitHubClient(token="mock_token")
    prs = await client.get_issue_linked_prs("kornia", "kornia", 6621)
    
    assert len(prs) == 1
    assert prs[0]["number"] == 6628
    assert prs[0]["author"] == "Debcode2006"
    assert prs[0]["state"] == "open"


@pytest.mark.asyncio
async def test_detect_linked_pr_kornia_6649(monkeypatch):
    """Verifies that issue #6649 is correctly flagged as having linked PR #6650 by 1sakshm."""
    mock_timeline = [
        {
            "event": "cross-referenced",
            "source": {
                "issue": {
                    "number": 6650,
                    "title": "docs(augmentation): a (a, b) shear is sampled from (a, b)",
                    "html_url": "https://github.com/kornia/kornia/pull/6650",
                    "state": "open",
                    "pull_request": {"url": "https://api.github.com/repos/kornia/kornia/pulls/6650"},
                    "user": {"login": "1sakshm", "avatar_url": "https://github.com/1sakshm.png"}
                }
            }
        }
    ]

    import httpx
    async def mock_get(self, url, headers=None, params=None):
        class MockResp:
            status_code = 200
            headers = {}
            def json(self):
                if "timeline" in url:
                    return mock_timeline
                return {"items": []}
        return MockResp()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = GitHubClient(token="mock_token")
    prs = await client.get_issue_linked_prs("kornia", "kornia", 6649)

    assert len(prs) == 1
    assert prs[0]["number"] == 6650
    assert prs[0]["author"] == "1sakshm"

    status = AvailabilityInspector.classify_issue_availability(
        assignees=[],
        is_reserved=False,
        linked_prs=prs
    )
    assert status == "PR_OPEN"
