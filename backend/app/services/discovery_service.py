import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
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

        http_sem = asyncio.Semaphore(6)

        async def _fetch_repo_batch(owner: str, repo_name: str, lang: str) -> List[Tuple[Dict[str, Any], str]]:
            async with http_sem:
                try:
                    raw = await self.gh.get_repo_issues(owner=owner, repo=repo_name, state="open", assignee="none", per_page=6)
                    return [(it, lang) for it in raw]
                except Exception as exc:
                    logger.warning(f"Failed syncing issues from {owner}/{repo_name}: {exc}")
                    return []

        repo_batches = await asyncio.gather(*[
            _fetch_repo_batch(o, r, l) for o, r, l in curated_repos
        ])
        raw_candidates: List[Tuple[Dict[str, Any], str]] = [pair for batch in repo_batches for pair in batch]

        # 2. Two grouped Search API queries across focus orgs (avoids 10/min Search rate limit & completes fast)
        grouped_queries = [
            (
                "gsoc:aiml:batch1:open:unassigned",
                "is:issue is:open no:assignee archived:false (org:numfocus OR org:numpy OR org:scipy OR org:pandas-dev OR org:matplotlib OR org:scikit-learn OR org:sympy OR org:astropy)",
            ),
            (
                "gsoc:aiml:batch2:open:unassigned",
                "is:issue is:open no:assignee archived:false (org:psf OR org:python OR org:pallets OR org:pypa OR org:deepchem OR org:kornia)",
            ),
        ]

        effective_pages = min(page_limit, 1 if force_refresh else page_limit)
        for query_key, search_query in grouped_queries:
            checkpoint_stmt = select(DiscoveryCheckpoint).where(DiscoveryCheckpoint.query_key == query_key)
            checkpoint = (await self.db.execute(checkpoint_stmt)).scalar_one_or_none()
            if not checkpoint:
                checkpoint = DiscoveryCheckpoint(query_key=query_key, last_page=1, items_synced=0)
                self.db.add(checkpoint)
                await self.db.flush()

            page = 1 if force_refresh else checkpoint.last_page
            for p in range(page, page + effective_pages):
                logger.info(f"Searching GSoC AI/ML issues: {query_key} (page {p})")
                search_data = await self.gh.search_issues(query=search_query, page=p, per_page=20)
                if search_data.get("rate_limited"):
                    errors.append(f"GitHub Search API rate limit reached on {query_key}.")
                    checkpoint.error_message = "Rate limit reached"
                    break
                if "error" in search_data:
                    errors.append(f"Error for {query_key}: {search_data['error']}")
                    break
                items = search_data.get("items", [])
                if not items:
                    checkpoint.is_complete = True
                    break
                for it in items:
                    raw_candidates.append((it, "Python"))
                checkpoint.last_page = p + 1
                checkpoint.items_synced += len(items)
                checkpoint.updated_at = datetime.utcnow()
                checkpoint.is_complete = False

        # 3. Pre-filter PRs, assigned/reserved/PR-intent issues & deduplicate before Timeline checks
        seen_keys = set()
        pristine_candidates: List[Tuple[Dict[str, Any], str, str, str, int]] = []
        for item, item_lang in raw_candidates:
            if "pull_request" in item or item.get("state") != "open":
                continue
            assignees = item.get("assignees") or []
            if assignees:
                continue
            repo_url = item.get("repository_url", "")
            parts = repo_url.rstrip("/").split("/")
            if len(parts) < 2:
                continue
            owner, repo_name = parts[-2], parts[-1]
            issue_num = item.get("number")
            if not issue_num:
                continue
            dedup_key = (owner.lower(), repo_name.lower(), int(issue_num))
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            title = item.get("title", "")
            body = item.get("body", "")
            is_res, _ = AvailabilityInspector.detect_maintainer_reservation(title=title, body=body)
            if is_res:
                continue
            has_pr_text, _ = AvailabilityInspector.detect_pr_intent_or_closure(f"{title}\n{body}")
            if has_pr_text:
                continue
            pristine_candidates.append((item, item_lang, owner, repo_name, int(issue_num)))

        # Concurrently verify linked PRs for top candidates (bounded to keep full scan ~3-8s)
        timeline_sem = asyncio.Semaphore(10)

        async def _check_linked_prs(o: str, r: str, n: int) -> List[Dict[str, Any]]:
            async with timeline_sem:
                try:
                    return await self.gh.get_issue_linked_prs(o, r, n)
                except Exception:
                    return []

        capped_candidates = pristine_candidates[:45]
        linked_results = await asyncio.gather(*[
            _check_linked_prs(o, r, n) for _, _, o, r, n in capped_candidates
        ])

        for (item, item_lang, _, _, _), prechecked_prs in zip(capped_candidates, linked_results):
            if prechecked_prs:
                continue
            try:
                await self._ingest_issue_item(item, item_lang, prechecked_linked_prs=prechecked_prs)
                total_discovered += 1
            except Exception as exc:
                logger.warning(f"Skipping issue during discovery ingestion: {exc}")

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
            "total_discovered": total_discovered,
            "items_synced": total_discovered,
            "errors": errors,
            "rate_limit_remaining": self.gh.rate_limit_remaining,
            "rate_limit_limit": self.gh.rate_limit_limit
        }

    async def _ingest_issue_item(
        self,
        item: Dict[str, Any],
        language: str,
        prechecked_linked_prs: Optional[List[Dict[str, Any]]] = None,
    ):
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

        # 5. Check assignees, maintainer reservations & active linked PRs (Strict Unassigned & PR-free enforcement)
        issue_number = item["number"]
        issue_stmt = select(Issue).where(
            Issue.repository_id == repository.id,
            Issue.issue_number == issue_number
        )
        res = await self.db.execute(issue_stmt)
        existing_issue = res.scalar_one_or_none()

        # Hard delete if assigned
        if assignees and len(assignees) > 0:
            if existing_issue:
                await self.db.delete(existing_issue)
            return

        # Hard delete if reserved for maintainers
        if is_reserved:
            if existing_issue:
                await self.db.delete(existing_issue)
            return

        # Hard delete if text explicitly states PR is linked or author is submitting PR
        full_text = f"{item.get('title', '')}\n{item.get('body', '')}"
        has_pr_text, _ = AvailabilityInspector.detect_pr_intent_or_closure(full_text)
        if has_pr_text:
            if existing_issue:
                await self.db.delete(existing_issue)
            return

        # Query GitHub timeline for linked open PRs unless already prechecked concurrently
        linked_prs = (
            prechecked_linked_prs
            if prechecked_linked_prs is not None
            else await self.gh.get_issue_linked_prs(repo_owner, repo_name, issue_number)
        )
        if linked_prs and len(linked_prs) > 0:
            # An active PR has been submitted to close this issue - hard delete immediately
            if existing_issue:
                await self.db.delete(existing_issue)
            return

        github_created_at = None
        if item.get("created_at"):
            try:
                github_created_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass

        if existing_issue:
            existing_issue.title = item.get("title", existing_issue.title)
            existing_issue.body = item.get("body", existing_issue.body)
            existing_issue.state = item.get("state", existing_issue.state)
            existing_issue.labels = raw_labels
            existing_issue.assignees = []
            existing_issue.comments_count = item.get("comments", existing_issue.comments_count)
            existing_issue.is_eligible = is_eligible
            existing_issue.ineligibility_reason = ineligibility_reason
            existing_issue.is_reserved = False
            existing_issue.reservation_reason = None
            existing_issue.has_open_pr = False
            existing_issue.linked_pr_count = 0
            existing_issue.linked_prs = []
            existing_issue.availability_status = "AVAILABLE"
            existing_issue.ranking_score = ranking_result["ranking_score"]
            existing_issue.difficulty_estimate = ranking_result["difficulty_estimate"]
            existing_issue.estimated_effort_hours = ranking_result["estimated_effort_hours"]
            existing_issue.ranking_breakdown = ranking_result["ranking_breakdown"]
            existing_issue.ai_summary = ranking_result["ai_summary"]
            existing_issue.last_verified_at = datetime.utcnow()
        else:
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
                assignees=[],
                comments_count=item.get("comments", 0),
                github_created_at=github_created_at,
                is_eligible=is_eligible,
                ineligibility_reason=ineligibility_reason,
                is_reserved=False,
                reservation_reason=None,
                availability_status="AVAILABLE",
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
