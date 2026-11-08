import re
import logging
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

# Patterns indicating that an issue is reserved by maintainers or restricted from general contribution
MAINTAINER_RESERVATION_PATTERNS = [
    re.compile(r"reserved\s+for\s+(a\s+)?maintainer(\s+implementation)?", re.IGNORECASE),
    re.compile(r"maintainer\s+implementation", re.IGNORECASE),
    re.compile(r"not\s+open\s+for\s+contribution", re.IGNORECASE),
    re.compile(r"internal\s+implementation", re.IGNORECASE),
    re.compile(r"maintainers?\s+only", re.IGNORECASE),
    re.compile(r"reserved\s+for\s+core\s+team", re.IGNORECASE),
    re.compile(r"core\s+team\s+only", re.IGNORECASE),
    re.compile(r"do\s+not\s+open\s+(a\s+)?pr", re.IGNORECASE),
    re.compile(r"pr(s)?\s+against\s+this\s+issue.*will\s+be\s+closed", re.IGNORECASE),
]

class AvailabilityInspector:
    """
    Analyzes issues for true community availability, checking for maintainer
    reservations, assignee presence, and active pull requests pending review.
    """

    @staticmethod
    def detect_maintainer_reservation(title: str, body: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Inspects title and body for maintainer reservation disclaimers (e.g. kornia#6640).
        Returns (is_reserved, reservation_reason).
        """
        text = f"{title or ''}\n{body or ''}"
        for pattern in MAINTAINER_RESERVATION_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_snippet = match.group(0).strip()
                reason = f"Reserved: Matches pattern '{matched_snippet}'"
                logger.info(f"Maintainer reservation detected: {reason}")
                return True, reason
        return False, None

    @staticmethod
    def classify_issue_availability(
        assignees: Optional[List[Any]] = None,
        is_reserved: bool = False,
        linked_prs: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Classifies an issue into one of 4 strict availability states:
        - RESERVED: Explicitly marked for maintainer implementation.
        - ASSIGNED: Has one or more assignees on GitHub.
        - PR_OPEN: Has active, unmerged pull requests attempting to close it.
        - AVAILABLE: Truly open, unassigned, with zero active PRs and no maintainer lock.
        """
        if is_reserved:
            return "RESERVED"

        # Check assignees
        has_assignees = False
        if assignees:
            if isinstance(assignees, list) and len(assignees) > 0:
                has_assignees = True
            elif isinstance(assignees, dict) and bool(assignees):
                has_assignees = True

        if has_assignees:
            return "ASSIGNED"

        # Check for open PRs
        if linked_prs:
            open_prs = [pr for pr in linked_prs if pr.get("state", "").lower() == "open"]
            if open_prs:
                return "PR_OPEN"

        return "AVAILABLE"
