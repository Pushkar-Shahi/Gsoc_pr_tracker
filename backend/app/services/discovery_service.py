import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Repository, Issue, DiscoveryCheckpoint, AuditLog
from app.services.github_client import GitHubClient
from app.services.ranking_service import RankingService
from app.services.availability_inspector import AvailabilityInspector
from app.core.config import settings
from app.core.gsoc_orgs import get_gsoc_info

logger = logging.getLogger(__name__)

class DiscoveryService:
    def __init__(self, db: AsyncSession, github_client: Optional[GitHubClient] = None, ranking_service: Optional[RankingService] = None):
        self.db = db
        self.gh = github_client or GitHubClient()
        self.ranking = ranking_service or RankingService()

    async def run_discovery_sync(
        self,
        language: Optional[str] = None,
        force_refresh: bool = False,
        page_limit: int = 2,
        gsoc_only: bool = False
    ) -> Dict[str, Any]:
        """
        Executes an incremental discovery query across GitHub's public API,
        evaluates eligibility, computes explainable rankings, and updates PostgreSQL.
        """
        languages = [language] if language else settings.DISCOVERY_LANGUAGES[:3]
        total_discovered = 0
        errors = []

        # Target curated repositories across the 4 organizations: NumFOCUS, PSF, DeepChem, Kornia
        curated_repos = [
            # NumFOCUS
            ("numpy", "numpy", "Python"),
            ("scipy", "scipy", "Python"),
            ("pandas-dev", "pandas", "Python"),
            ("matplotlib", "matplotlib", "Python"),
            ("scikit-learn", "scikit-learn", "Python"),
            ("sympy", "sympy", "Python"),
            ("astropy", "astropy", "Python"),
            # Python Software Foundation
            ("psf", "requests", "Python"),
            ("psf", "black", "Python"),
            ("python", "cpython", "Python"),
            ("pallets", "flask", "Python"),
            ("pypa", "pip", "Python"),
            # DeepChem
            ("deepchem", "deepchem", "Python"),
            # Kornia
            ("kornia", "kornia", "Python"),
        ]

        # 1. Sync curated repositories for verified open unassigned issues
        for owner, repo_name, lang in curated_repos:
            try:
                repo_issues = await self.gh.get_repo_issues(owner=owner, repo=repo_name, state="open", assignee="none", per_page=10)
                for item in repo_issues:
                    await self._ingest_issue_item(item, lang)
                    total_discovered += 1
                await self.db.commit()
            except Exception as e:
                logger.warning(f"Failed syncing issues from {owner}/{repo_name}: {e}")

        # 2. Targeted search queries across the 4 organizations
        focus_orgs = [
            "numfocus", "numpy", "scipy", "pandas-dev", "matplotlib", "scikit-learn", "sympy",
            "psf", "python", "pallets", "pypa",
            "deepchem",
            "kornia",
        ]
        for org in focus_orgs:
            query_key = f"gsoc:aiml:{org}:open:unassigned"
            checkpoint_stmt = select(DiscoveryCheckpoint).where(DiscoveryCheckpoint.query_key == query_key)
            result = await self.db.execute(checkpoint_stmt)
            checkpoint = result.scalar_one_or_none()

            if not checkpoint:
                checkpoint = DiscoveryCheckpoint(query_key=query_key, last_page=1, items_synced=0)
                self.db.add(checkpoint)
                await self.db.flush()

            page = 1 if force_refresh else checkpoint.last_page
            query = f"is:issue is:open no:assignee archived:false org:{org}"

            for p in range(page, page + page_limit):
                logger.info(f"Searching GSoC AI/ML issues: {query} (page {p})")
                search_data = await self.gh.search_issues(query=query, page=p, per_page=15)

                if search_data.get("rate_limited"):
                    errors.append(f"GitHub API Rate Limit reached while scanning {org}.")
                    checkpoint.error_message = "Rate limit reached"
                    break

                if "error" in search_data:
                    errors.append(f"Error for {org}: {search_data['error']}")
                    break

                items = search_data.get("items", [])
                if not items:
                    checkpoint.is_complete = True
                    break

                for item in items:
                    await self._ingest_issue_item(item, "Python")
                    total_discovered += 1

                checkpoint.last_page = p + 1
                checkpoint.items_synced += len(items)
                checkpoint.updated_at = datetime.utcnow()
                checkpoint.is_complete = False
                await self.db.commit()

        # Audit event
        audit = AuditLog(
            action="DISCOVERY_SYNC",
            actor="SYSTEM",
            details={
                "items_synced": total_discovered,
                "languages": languages,
                "errors": errors,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        self.db.add(audit)
        await self.db.commit()

        return {
            "items_synced": total_discovered,
            "errors": errors,
            "rate_limit_remaining": self.gh.rate_limit_remaining,
            "rate_limit_limit": self.gh.rate_limit_limit
        }

    async def _ingest_issue_item(self, item: Dict[str, Any], language: str):
        """Processes an individual GitHub issue item into database with ranking and eligibility checks."""
        # Check if item is a PR
        if "pull_request" in item:
            return

        # Parse repository owner and name from repository_url
        # Example: https://api.github.com/repos/pallets/flask
        repo_url = item.get("repository_url", "")
        parts = repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            return
        repo_owner, repo_name = parts[-2], parts[-1]
        repo_full_name = f"{repo_owner}/{repo_name}"

        # 1. Fetch or create repository record
        repo_stmt = select(Repository).where(Repository.full_name == repo_full_name)
        result = await self.db.execute(repo_stmt)
        repository = result.scalar_one_or_none()

        gsoc_name = get_gsoc_info(repo_owner, repo_name)

        if not repository:
            # Fetch repository details to verify stars and license
            repo_info = await self.gh.get_repository(repo_owner, repo_name)
            stars = repo_info.get("stargazers_count", 0) if repo_info else 0
            lic_data = repo_info.get("license") if repo_info else None
            spdx = lic_data.get("spdx_id") if lic_data else None
            lic_name = lic_data.get("name") if lic_data else None
            is_archived = repo_info.get("archived", False) if repo_info else False
            default_branch = repo_info.get("default_branch", "main") if repo_info else "main"

            repository = Repository(
                owner=repo_owner,
                name=repo_name,
                full_name=repo_full_name,
                html_url=f"https://github.com/{repo_full_name}",
                default_branch=default_branch,
                primary_language=language,
                license_spdx=spdx,
                license_name=lic_name,
                stars_count=stars,
                is_archived=is_archived,
                is_gsoc=(gsoc_name is not None),
                gsoc_org_name=gsoc_name,
                last_inspected_at=datetime.utcnow()
            )
            self.db.add(repository)
            await self.db.flush()
        elif not repository.is_gsoc and gsoc_name:
            repository.is_gsoc = True
            repository.gsoc_org_name = gsoc_name

        # 2. Check eligibility
        is_eligible = True
        ineligibility_reason = None
        
        # Check assignees
        assignees = item.get("assignees", [])
        if assignees and len(assignees) > 0:
            is_eligible = False
            ineligibility_reason = "Issue already has assigned contributors."

        # Check state
        if item.get("state") != "open":
            is_eligible = False
            ineligibility_reason = "Issue is closed."

        # Check repository archive
        if repository.is_archived:
            is_eligible = False
            ineligibility_reason = "Repository is archived."

        # Check bot author
        author_login = item.get("user", {}).get("login", "")
        if "bot" in author_login.lower():
            is_eligible = False
            ineligibility_reason = "Issue filed by automated bot."

        # Check blocked labels
        raw_labels = item.get("labels", [])
        label_names = [l.get("name", "").lower() for l in raw_labels if isinstance(l, dict)]
        for bl in settings.BLOCKED_LABELS:
            if bl in label_names:
                is_eligible = False
                ineligibility_reason = f"Contains blocked label: '{bl}'."
                break

        # 3. Compute explainable ranking
        ranking_result = self.ranking.evaluate_issue(
            title=item.get("title", ""),
            body=item.get("body", ""),
            labels=raw_labels,
            repo_language=language,
            repo_stars=repository.stars_count,
            license_spdx=repository.license_spdx
        )

        # 4. Check license status & maintainer reservation
        license_status = "UNKNOWN"
        if repository.license_spdx and repository.license_spdx not in ("NOASSERTION", None):
            license_status = "VERIFIED_OSI"
        elif repository.license_name:
            license_status = "UNKNOWN"
        else:
            license_status = "NO_LICENSE"

        is_reserved, reservation_reason = AvailabilityInspector.detect_maintainer_reservation(
            title=item.get("title", ""),
            body=item.get("body", "")
        )

        # 5. Insert or update Issue
        issue_number = item["number"]
        issue_stmt = select(Issue).where(
            Issue.repository_id == repository.id,
            Issue.issue_number == issue_number
        )
        res = await self.db.execute(issue_stmt)
        existing_issue = res.scalar_one_or_none()

        github_created_at = None
        if item.get("created_at"):
            try:
                github_created_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass

        if existing_issue:
            existing_prs = existing_issue.linked_prs or []
            availability_status = AvailabilityInspector.classify_issue_availability(
                assignees=assignees,
                is_reserved=is_reserved,
                linked_prs=existing_prs
            )
            existing_issue.title = item.get("title", existing_issue.title)
            existing_issue.body = item.get("body", existing_issue.body)
            existing_issue.state = item.get("state", existing_issue.state)
            existing_issue.labels = raw_labels
            existing_issue.assignees = assignees
            existing_issue.comments_count = item.get("comments", existing_issue.comments_count)
            existing_issue.is_eligible = is_eligible
            existing_issue.ineligibility_reason = ineligibility_reason
            existing_issue.is_reserved = is_reserved
            existing_issue.reservation_reason = reservation_reason
            existing_issue.availability_status = availability_status
            existing_issue.ranking_score = ranking_result["ranking_score"]
            existing_issue.difficulty_estimate = ranking_result["difficulty_estimate"]
            existing_issue.estimated_effort_hours = ranking_result["estimated_effort_hours"]
            existing_issue.ranking_breakdown = ranking_result["ranking_breakdown"]
            existing_issue.ai_summary = ranking_result["ai_summary"]
            existing_issue.last_verified_at = datetime.utcnow()
        else:
            availability_status = AvailabilityInspector.classify_issue_availability(
                assignees=assignees,
                is_reserved=is_reserved,
                linked_prs=[]
            )
            new_issue = Issue(
                repository_id=repository.id,
                github_id=item["id"],
                issue_number=issue_number,
                title=item.get("title", ""),
                body=item.get("body", ""),
                author=author_login,
                html_url=item.get("html_url", ""),
                state=item.get("state", "open"),
                labels=raw_labels,
                assignees=assignees,
                comments_count=item.get("comments", 0),
                github_created_at=github_created_at,
                is_eligible=is_eligible,
                ineligibility_reason=ineligibility_reason,
                is_reserved=is_reserved,
                reservation_reason=reservation_reason,
                availability_status=availability_status,
                has_open_pr=False,
                linked_pr_count=0,
                linked_prs=[],
                license_status=license_status,
                ranking_score=ranking_result["ranking_score"],
                difficulty_estimate=ranking_result["difficulty_estimate"],
                estimated_effort_hours=ranking_result["estimated_effort_hours"],
                ranking_breakdown=ranking_result["ranking_breakdown"],
                ai_summary=ranking_result["ai_summary"],
                last_verified_at=datetime.utcnow()
            )
            self.db.add(new_issue)
