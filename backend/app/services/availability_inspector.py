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

# Patterns indicating that an open PR is linked, submitted, or in-progress to close this issue
PR_CLOSURE_OR_INTENT_PATTERNS = [
    # Exact sentence from GitHub timeline (user screenshot): "<user> linked a pull request that will close this issue"
    re.compile(r"\blinked\s+a\s+pull\s+request\s+that\s+will\s+close\s+this\s+issue\b", re.IGNORECASE),
    re.compile(r"\blinked\s+a\s+pull\s+request\b", re.IGNORECASE),
    re.compile(r"\bclosedByPullRequestsReferences\b", re.IGNORECASE),
    re.compile(r"\blinkedPullRequests\b", re.IGNORECASE),
    # Author / contributor stating they have opened or will open a PR (e.g. 1sakshm: "I'll open a PR with the docstring fix")
    re.compile(r"\b(?:I'll|I\s+will|I've|I\s+have)\s+open(?:ed)?\s+a\s+(?:new\s+)?PR\b", re.IGNORECASE),
    re.compile(r"\b(?:I'll|I\s+will|I've|I\s+have)\s+submit(?:ted)?\s+a\s+(?:new\s+)?PR\b", re.IGNORECASE),
    re.compile(r"\b(?:I'm|I\s+am)\s+working\s+on\s+a\s+PR\b", re.IGNORECASE),
    re.compile(r"\b(?:PR|pull\s+request)\s+#?\d+\s+(?:will\s+close|fixes|resolves|addresses)\b", re.IGNORECASE),
    re.compile(r"\b(?:fixes|closes|resolves)\s+(?:this\s+issue\s+in\s+)?(?:PR|pull\s+request)\s+#?\d+\b", re.IGNORECASE),
]

class AvailabilityInspector:
    """
    Analyzes issues for true community availability, checking for maintainer
    reservations, assignee presence, and active pull requests pending review.
    """

    @staticmethod
    def detect_pr_intent_or_closure(text: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Inspects text (issue body, comments, or timeline text) for explicit PR closures
        or intent to submit PRs (e.g. '1sakshm linked a pull request that will close this issue').
        Returns (has_pr, matched_reason).
        """
        if not text:
            return False, None
        for pattern in PR_CLOSURE_OR_INTENT_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_snippet = match.group(0).strip()
                reason = f"Active PR detected via pattern: '{matched_snippet}'"
                logger.info(f"PR closure pattern detected: {reason}")
                return True, reason
        return False, None

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
        linked_prs: Optional[List[Dict[str, Any]]] = None,
        body_text: Optional[str] = None
    ) -> str:
        """
        Classifies an issue into one of 4 strict availability states:
        - RESERVED: Explicitly marked for maintainer implementation.
        - ASSIGNED: Has one or more assignees on GitHub.
        - PR_OPEN: Has active, unmerged pull requests attempting to close it or explicit PR intent.
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

        # Check PR intent or closure from text
        if body_text:
            has_pr_text, _ = AvailabilityInspector.detect_pr_intent_or_closure(body_text)
            if has_pr_text:
                return "PR_OPEN"

        # Check for open PRs
        if linked_prs:
            open_prs = [pr for pr in linked_prs if pr.get("state", "").lower() == "open"]
            if open_prs:
                return "PR_OPEN"

        return "AVAILABLE"

