import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from app.core.config import settings

logger = logging.getLogger(__name__)

class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.GITHUB_TOKEN
        self.base_url = settings.GITHUB_API_BASE
        self.rate_limit_remaining = 60
        self.rate_limit_limit = 60
        self.rate_limit_reset = None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": settings.GITHUB_API_VERSION,
            "User-Agent": "Issue-to-PR-Platform/1.0"
        }
        if self.token and self.token.strip():
            headers["Authorization"] = f"Bearer {self.token.strip()}"
        return headers

    def _update_rate_limits(self, response: httpx.Response):
        if "x-ratelimit-remaining" in response.headers:
            try:
                self.rate_limit_remaining = int(response.headers["x-ratelimit-remaining"])
                self.rate_limit_limit = int(response.headers.get("x-ratelimit-limit", 60))
                reset_ts = int(response.headers.get("x-ratelimit-reset", 0))
                if reset_ts:
                    self.rate_limit_reset = datetime.fromtimestamp(reset_ts, timezone.utc).replace(tzinfo=None)
            except Exception as e:
                logger.debug(f"Failed to parse rate limit headers: {e}")

    async def get_authenticated_user(self) -> Optional[Dict[str, Any]]:
        """Fetch authenticated user profile if token provided."""
        if not self.token:
            return None
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{self.base_url}/user", headers=self._get_headers())
                self._update_rate_limits(resp)
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"Failed to fetch authenticated user: {resp.status_code} {resp.text}")
                return None
            except Exception as e:
                logger.error(f"Error fetching user: {e}")
                return None

    async def search_issues(
        self,
        query: str,
        page: int = 1,
        per_page: int = 30,
        sort: str = "updated",
        order: str = "desc"
    ) -> Dict[str, Any]:
        """Search public open unassigned issues across GitHub."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            params = {
                "q": query,
                "page": page,
                "per_page": per_page,
                "sort": sort,
                "order": order
            }
            try:
                resp = await client.get(
                    f"{self.base_url}/search/issues",
                    headers=self._get_headers(),
                    params=params
                )
                self._update_rate_limits(resp)
                
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code in (403, 429):
                    logger.warning(f"GitHub search rate limit exceeded: {resp.text}")
                    return {"total_count": 0, "items": [], "rate_limited": True}
                else:
                    logger.error(f"Search API returned error {resp.status_code}: {resp.text}")
                    return {"total_count": 0, "items": [], "error": resp.text}
            except Exception as e:
                logger.error(f"Exception during search_issues: {e}")
                return {"total_count": 0, "items": [], "error": str(e)}

    async def get_repository(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Fetch repository details, stars, license, permissions."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}",
                    headers=self._get_headers()
                )
                self._update_rate_limits(resp)
                if resp.status_code == 200:
                    return resp.json()
                return None
            except Exception as e:
                logger.error(f"Error fetching repo {owner}/{repo}: {e}")
                return None

    async def get_repo_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        assignee: Optional[str] = None,
        per_page: int = 30
    ) -> List[Dict[str, Any]]:
        """Fetch open non-PR issues directly from a target repository."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                params = {"state": state, "per_page": per_page}
                if assignee is not None:
                    params["assignee"] = assignee
                resp = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/issues",
                    params=params,
                    headers=self._get_headers()
                )
                self._update_rate_limits(resp)
                if resp.status_code == 200:
                    data = resp.json()
                    # Filter out pull requests
                    return [item for item in data if isinstance(item, dict) and "pull_request" not in item]
                return []
            except Exception as e:
                logger.error(f"Error fetching repo issues for {owner}/{repo}: {e}")
                return []

    async def get_issue(self, owner: str, repo: str, issue_number: int) -> Optional[Dict[str, Any]]:
        """Fetch single issue with up-to-date assignees and state."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}",
                    headers=self._get_headers()
                )
                self._update_rate_limits(resp)
                if resp.status_code == 200:
                    return resp.json()
                return None
            except Exception as e:
                logger.error(f"Error fetching issue #{issue_number}: {e}")
                return None

    async def get_file_content(self, owner: str, repo: str, path: str) -> Optional[str]:
        """Fetch text content of a repository file (e.g. CONTRIBUTING.md, README.md)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/contents/{path}",
                    headers={**self._get_headers(), "Accept": "application/vnd.github.raw+json"}
                )
                self._update_rate_limits(resp)
                if resp.status_code == 200:
                    return resp.text
                return None
            except Exception as e:
                logger.debug(f"Could not read {path} from {owner}/{repo}: {e}")
                return None

    async def post_issue_comment(self, owner: str, repo: str, issue_number: int, comment_body: str) -> Dict[str, Any]:
        """Post an assignment request comment to an issue after explicit user approval."""
        if not self.token:
            return {"success": False, "error": "GitHub Personal Access Token is required to post comments."}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments",
                    headers=self._get_headers(),
                    json={"body": comment_body}
                )
                self._update_rate_limits(resp)
                if resp.status_code == 201:
                    data = resp.json()
                    return {"success": True, "comment_id": str(data.get("id")), "html_url": data.get("html_url")}
                return {"success": False, "status_code": resp.status_code, "error": resp.text}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def create_fork(self, owner: str, repo: str) -> Dict[str, Any]:
        """Create a user fork of the repository if no direct write access exists."""
        if not self.token:
            return {"success": False, "error": "GitHub Token required to fork repository."}
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/repos/{owner}/{repo}/forks",
                    headers=self._get_headers()
                )
                self._update_rate_limits(resp)
                if resp.status_code in (200, 202):
                    fork_data = resp.json()
                    return {
                        "success": True,
                        "fork_owner": fork_data["owner"]["login"],
                        "fork_url": fork_data["clone_url"],
                        "html_url": fork_data["html_url"]
                    }
                return {"success": False, "error": resp.text}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def create_pull_request(
        self,
        upstream_owner: str,
        upstream_repo: str,
        title: str,
        body: str,
        head: str,
        base: str
    ) -> Dict[str, Any]:
        """Create a pull request against upstream repository."""
        if not self.token:
            return {"success": False, "error": "GitHub Token required to create a pull request."}
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                payload = {
                    "title": title,
                    "body": body,
                    "head": head,
                    "base": base
                }
                resp = await client.post(
                    f"{self.base_url}/repos/{upstream_owner}/{upstream_repo}/pulls",
                    headers=self._get_headers(),
                    json=payload
                )
                self._update_rate_limits(resp)
                if resp.status_code == 201:
                    pr_data = resp.json()
                    return {
                        "success": True,
                        "pr_number": pr_data.get("number"),
                        "pr_url": pr_data.get("html_url"),
                        "state": pr_data.get("state")
                    }
                return {"success": False, "status_code": resp.status_code, "error": resp.text}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def get_pull_request(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        """Fetch real-time pull request state, merge status, and head commit SHA."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}",
                    headers=self._get_headers()
                )
                self._update_rate_limits(resp)
                if resp.status_code == 200:
                    return resp.json()
                return None
            except Exception as e:
                logger.error(f"Error fetching PR #{pr_number} from {owner}/{repo}: {e}")
                return None

    async def get_pull_request_reviews(self, owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Fetch maintainer review states and feedback comments for a PR."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                    headers=self._get_headers()
                )
                self._update_rate_limits(resp)
                if resp.status_code == 200:
                    return resp.json()
                return []
            except Exception as e:
                logger.error(f"Error fetching reviews for PR #{pr_number}: {e}")
                return []

    async def get_commit_check_runs(self, owner: str, repo: str, ref: str) -> Dict[str, Any]:
        """Fetch CI check runs for a commit ref to assess build / test status."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/commits/{ref}/check-runs",
                    headers=self._get_headers()
                )
                self._update_rate_limits(resp)
                if resp.status_code == 200:
                    data = resp.json()
                    check_runs = data.get("check_runs", [])
                    if not check_runs:
                        return {"status": "none", "total": 0, "runs": []}

                    # Determine aggregate status
                    conclusions = [r.get("conclusion") for r in check_runs]
                    statuses = [r.get("status") for r in check_runs]

                    if any(c in ("failure", "timed_out", "action_required") for c in conclusions):
                        overall = "failure"
                    elif any(s in ("queued", "in_progress") for s in statuses):
                        overall = "pending"
                    elif all(c in ("success", "neutral", "skipped") for c in conclusions):
                        overall = "success"
                    else:
                        overall = "pending"

                    return {
                        "status": overall,
                        "total": len(check_runs),
                        "runs": [
                            {
                                "name": r.get("name"),
                                "status": r.get("status"),
                                "conclusion": r.get("conclusion"),
                                "html_url": r.get("html_url")
                            }
                            for r in check_runs
                        ]
                    }
                return {"status": "unknown", "total": 0, "runs": []}
            except Exception as e:
                logger.error(f"Error fetching check runs for ref {ref}: {e}")
                return {"status": "error", "total": 0, "error": str(e), "runs": []}

    async def find_existing_pull_request(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        branch_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Detects pre-existing or newly opened pull requests that would make submission duplicative.
        Checks for references to the issue or matching branch name.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/pulls",
                    headers=self._get_headers(),
                    params={"state": "open", "per_page": 50}
                )
                self._update_rate_limits(resp)
                if resp.status_code == 200:
                    pulls = resp.json()
                    issue_ref_patterns = [
                        f"#{issue_number}",
                        f"fixes #{issue_number}",
                        f"closes #{issue_number}",
                        f"resolves #{issue_number}"
                    ]
                    for pr in pulls:
                        pr_title = (pr.get("title") or "").lower()
                        pr_body = (pr.get("body") or "").lower()
                        pr_head_ref = pr.get("head", {}).get("ref", "")

                        # Check branch match
                        if branch_name and pr_head_ref == branch_name:
                            return pr

                        # Check issue number reference in title or body
                        for pat in issue_ref_patterns:
                            if pat in pr_title or pat in pr_body:
                                return pr

                return None
            except Exception as e:
                logger.error(f"Error checking duplicate PRs in {owner}/{repo}: {e}")
                return None
