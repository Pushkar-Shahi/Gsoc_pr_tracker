import re
import logging
from typing import Dict, Any, List, Optional
from app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)

class PolicyInspector:
    def __init__(self, github_client: Optional[GitHubClient] = None):
        self.gh = github_client or GitHubClient()

    async def inspect_repository_policy(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        issue_body: str,
        issue_labels: List[Any],
        issue_assignees: List[Any]
    ) -> Dict[str, Any]:
        """
        Inspects contributing guides, README, and issue signals to determine
        if assignment approval is mandatory before coding.
        """
        evidence = []
        assignment_required = False
        policy_review_required = False
        blocked = False
        blocked_reason = None
        
        # 1. Check if already assigned
        if issue_assignees and len(issue_assignees) > 0:
            assigned_logins = [a.get("login") if isinstance(a, dict) else str(a) for a in issue_assignees]
            blocked = True
            blocked_reason = f"Issue is already assigned to {', '.join(assigned_logins)}."
            evidence.append(blocked_reason)
            return {
                "workflow_state": "BLOCKED",
                "assignment_required": False,
                "draft_comment": None,
                "evidence": evidence,
                "license_status": "VERIFIED",
                "recommendation": blocked_reason
            }

        # 2. Check repo metadata and license
        repo_data = await self.gh.get_repository(owner, repo)
        license_status = "UNKNOWN"
        license_name = None
        
        if repo_data:
            if repo_data.get("archived") or repo_data.get("disabled"):
                evidence.append("Repository is archived or disabled.")
                return {
                    "workflow_state": "BLOCKED",
                    "assignment_required": False,
                    "draft_comment": None,
                    "evidence": evidence,
                    "license_status": "RESTRICTIVE",
                    "recommendation": "Repository is archived; pull requests cannot be accepted."
                }
            
            lic = repo_data.get("license")
            if lic:
                license_status = "VERIFIED_OSI" if lic.get("spdx_id") not in ("NOASSERTION", None) else "UNKNOWN"
                license_name = lic.get("name") or lic.get("spdx_id")
                evidence.append(f"Repository license detected: {license_name} ({license_status}).")
            else:
                license_status = "NO_LICENSE"
                evidence.append("Warning: No open-source license found in repository.")
                policy_review_required = True

        # 3. Read CONTRIBUTING.md files
        contributing_text = None
        for path in ["CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"]:
            content = await self.gh.get_file_content(owner, repo, path)
            if content:
                contributing_text = content
                evidence.append(f"Inspected guidelines in `{path}`.")
                break

        # Check for assignment patterns in CONTRIBUTING.md or issue body
        assignment_patterns = [
            r"ask to be assigned",
            r"comment to claim",
            r"comment before starting",
            r"wait for assignment",
            r"must be assigned",
            r"assigned by a maintainer",
            r"please do not open a pr without",
            r"claim this issue",
            r"request assignment",
            r"comment below if you would like to work"
        ]

        text_to_search = f"{(contributing_text or '')} {(issue_body or '')}".lower()
        matched_patterns = []
        for pat in assignment_patterns:
            if re.search(pat, text_to_search):
                matched_patterns.append(pat)

        label_names = [
            (lbl["name"].lower() if isinstance(lbl, dict) else str(lbl).lower())
            for lbl in issue_labels
        ]

        if any("claimed" in l or "in progress" in l for l in label_names):
            blocked = True
            blocked_reason = "Issue labels indicate it is already claimed or in progress."
            evidence.append(blocked_reason)

        if matched_patterns:
            assignment_required = True
            evidence.append(f"Repository contribution instructions state: '{matched_patterns[0]}'.")

        # Draft assignment request if required
        draft_comment = None
        if assignment_required:
            draft_comment = (
                f"Hi @{owner} team! I would love to work on this issue #{issue_number}. "
                f"Could you please assign this to me if it is still available? "
                f"I plan to follow the contribution guidelines and submit a clean PR with tests. Thank you!"
            )

        # Decide workflow state
        if blocked:
            workflow_state = "BLOCKED"
            recommendation = blocked_reason or "Contribution cannot proceed."
        elif assignment_required:
            workflow_state = "ASSIGNMENT_REQUEST_REQUIRED"
            recommendation = "Repository guidelines require maintainer assignment approval before coding begins. Review the draft comment below."
        elif policy_review_required:
            workflow_state = "POLICY_REVIEW_REQUIRED"
            recommendation = "Repository lacks an OSI open-source license or has ambiguous rules. Review policy before proceeding."
        else:
            workflow_state = "READY_TO_WORK"
            recommendation = "No prior assignment prerequisite found. Ready to prepare isolated workspace in Antigravity."

        return {
            "workflow_state": workflow_state,
            "assignment_required": assignment_required,
            "draft_comment": draft_comment,
            "evidence": evidence,
            "license_status": license_status,
            "recommendation": recommendation
        }
