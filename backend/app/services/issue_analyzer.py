import re
import logging
from typing import Dict, Any, List, Optional
from app.services.github_client import GitHubClient
from app.services.policy_inspector import PolicyInspector
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

class IssueAnalyzer:
    def __init__(self, github_client: Optional[GitHubClient] = None):
        self.gh = github_client or GitHubClient()
        self.policy_inspector = PolicyInspector(github_client=self.gh)

    async def analyze_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        title: str,
        body: str,
        labels: List[Any],
        language: Optional[str] = None,
        assignees: Optional[List[Any]] = None,
        ai_api_key: Optional[str] = None,
        ai_provider: Optional[str] = None,
        custom_endpoint: Optional[str] = None,
        ai_key_source: Optional[str] = None,
        triage_policy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Performs deep automated intelligence on a GitHub issue:
        1. Contextual summary & executive overview
        2. Root cause analysis & reproduction signals
        3. Inferred file paths and codebase components
        4. Step-by-step surgical implementation plan
        5. Prescribed test command and regression verification
        6. Repository contribution rule check (Assignment required vs Direct PR permitted)
        """
        body_text = body or ""
        lang = (language or "generic").lower()
        
        # 1. Inspect repository policy & rule
        policy_result = await self.policy_inspector.inspect_repository_policy(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            issue_body=body_text,
            issue_labels=labels or [],
            issue_assignees=assignees or []
        )
        
        assignment_required = policy_result.get("assignment_required", False)
        workflow_state = policy_result.get("workflow_state", "READY_TO_WORK")
        policy_evidence = list(policy_result.get("evidence", []))

        if triage_policy and triage_policy.get("require_maintainer_approval"):
            assignment_required = True
            workflow_state = "ASSIGNMENT_REQUIRED"
            policy_evidence.append("Organization triage policy requires maintainer approval before PR submission.")
        
        # 2. Extract code blocks, error traces, and mentioned files
        extracted_files = self._extract_file_paths(body_text, lang)
        extracted_errors = self._extract_error_traces(body_text)
        issue_category = self._classify_issue_category(title, body_text, labels)
        
        # 3. Determine testing framework and command
        test_strategy = self._determine_test_strategy(lang, body_text)
        
        # 4. Formulate executive summary & root cause hypothesis
        executive_summary = self._generate_executive_summary(title, body_text, issue_category, lang)
        root_cause = self._analyze_root_cause(title, body_text, extracted_errors, issue_category)
        
        # 5. Formulate step-by-step surgical fix plan
        proposed_plan = self._generate_implementation_steps(
            issue_category=issue_category,
            title=title,
            affected_files=extracted_files,
            test_strategy=test_strategy
        )

        # 5b. Enrich with real BYOK LLM brief when configured
        ai_mode = "deterministic_heuristic"
        llm_brief = None
        if ai_api_key:
            llm_brief = await LLMService.generate_issue_brief(
                api_key=ai_api_key,
                provider=ai_provider or "gemini",
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                title=title,
                body=body_text,
                language=language,
                custom_endpoint=custom_endpoint,
            )
        if llm_brief:
            ai_mode = "live_byok"
            if llm_brief.get("executive_summary"):
                executive_summary = llm_brief["executive_summary"]
            if llm_brief.get("root_cause_analysis"):
                root_cause = llm_brief["root_cause_analysis"]
            if llm_brief.get("affected_files"):
                extracted_files = llm_brief["affected_files"]
            if llm_brief.get("proposed_plan"):
                proposed_plan = llm_brief["proposed_plan"]
            if llm_brief.get("test_command"):
                test_strategy["command"] = llm_brief["test_command"]
        
        # 6. Tailor assignment comment if required
        draft_comment = policy_result.get("draft_comment")
        if assignment_required and not draft_comment:
            draft_comment = (
                f"Hi @{owner} team! I analyzed issue #{issue_number} ('{title}') and would love to work on this. "
                f"I plan to follow the contribution guidelines, implement the fix in `{extracted_files[0] if extracted_files else 'the target module'}`, "
                f"and verify it with `{test_strategy['command']}` before opening a PR. Could you please assign this to me if available? Thank you!"
            )

        rule_decision = {
            "assignment_required": assignment_required,
            "workflow_state": workflow_state,
            "rule_title": "Maintainer Pre-Assignment Required" if assignment_required else "Direct Contribution Permitted",
            "rule_explanation": (
                "Repository contributing guidelines require maintainer approval before coding begins to prevent duplicate work."
                if assignment_required else
                "Repository allows direct branch preparation and pull requests without prior issue assignment."
            ),
            "evidence": policy_evidence,
            "action_on_approval": (
                "Submit assignment request comment to maintainers and wait for maintainer assignment approval."
                if assignment_required else
                "Prepare isolated Git worktree & branch immediately, launch workspace, and begin fix execution."
            ),
            "draft_comment": draft_comment
        }

        return {
            "analyzed_at": "now",
            "issue_number": issue_number,
            "repository": f"{owner}/{repo}",
            "title": title,
            "category": issue_category,
            "primary_language": lang,
            "executive_summary": executive_summary,
            "root_cause_analysis": root_cause,
            "extracted_errors": extracted_errors[:3],
            "affected_files": extracted_files,
            "proposed_plan": proposed_plan,
            "test_strategy": test_strategy,
            "rule_check": rule_decision,
            "ai_mode": ai_mode,
            "ai_provider": ai_provider or "gemini",
            "ai_key_source": ai_key_source or "none",
            "prompt_text": self._generate_agent_prompt(
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                title=title,
                body=body_text,
                plan=proposed_plan,
                files=extracted_files,
                test_cmd=test_strategy["command"]
            )
        }

    def _extract_file_paths(self, text: str, lang: str) -> List[str]:
        """Finds source file paths mentioned in the issue body or error trace."""
        # Regex matching common file paths
        pattern = r'(?:[a-zA-Z0-9_\-\.\@\/]+)\.(?:py|ts|tsx|js|jsx|go|rs|cpp|c|h|java|rb|php|json|yml|yaml|toml|md)'
        matches = re.findall(pattern, text)
        
        # Deduplicate while preserving order and filtering noise
        clean_paths = []
        noise = {"package.json", "tsconfig.json", "cargo.toml", "readme.md", "contributing.md", ".github"}
        
        for m in matches:
            m_clean = m.strip("`'\"(),;:")
            # Filter out URLs or pure filenames without extensions
            if "/" in m_clean and not m_clean.startswith("http"):
                if m_clean.lower() not in [p.lower() for p in clean_paths]:
                    clean_paths.append(m_clean)
            elif m_clean.lower() not in noise and "." in m_clean:
                if m_clean.lower() not in [p.lower() for p in clean_paths]:
                    clean_paths.append(m_clean)

        # If none found, provide plausible default entry points based on language
        if not clean_paths:
            if lang in ("typescript", "javascript"):
                clean_paths = ["src/index.ts", "src/App.tsx", "package.json"]
            elif lang == "python":
                clean_paths = ["app/main.py", "tests/test_main.py"]
            elif lang == "go":
                clean_paths = ["main.go", "pkg/"]
            elif lang == "rust":
                clean_paths = ["src/lib.rs", "src/main.rs"]
            else:
                clean_paths = ["src/"]

        return clean_paths[:6]

    def _extract_error_traces(self, text: str) -> List[str]:
        """Extracts stack traces, exception messages, and command outputs from markdown code blocks."""
        code_blocks = re.findall(r'```(?:[a-zA-Z0-9_\-]*\n)?(.*?)```', text, re.DOTALL)
        errors = []
        for block in code_blocks:
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            for line in lines:
                if any(k in line.lower() for k in ["error:", "exception:", "failed:", "fatal:", "panic:", "traceback", "ts2", "err_"]):
                    errors.append(line[:160])
        return list(dict.fromkeys(errors))[:4]

    def _classify_issue_category(self, title: str, body: str, labels: List[Any]) -> str:
        """Classifies issue into standard bug, feature, refactor, docs, or test."""
        combined = f"{title} {body}".lower()
        label_names = [
            (l.get("name", "").lower() if isinstance(l, dict) else str(l).lower())
            for l in labels
        ]

        if any(l in ["bug", "defect", "fix", "regression"] for l in label_names) or "bug" in combined or "error" in combined or "fix" in combined:
            return "bug"
        if any(l in ["enhancement", "feature", "feat"] for l in label_names) or "feature" in combined or "support" in combined or "add " in combined:
            return "feature"
        if any(l in ["refactor", "cleanup", "chore"] for l in label_names) or "refactor" in combined:
            return "refactor"
        if any(l in ["documentation", "docs"] for l in label_names) or "docs" in combined or "readme" in combined:
            return "documentation"
        return "bug"

    def _determine_test_strategy(self, lang: str, text: str) -> Dict[str, Any]:
        """Selects appropriate testing command and criteria."""
        lower_text = text.lower()
        if lang in ("typescript", "javascript"):
            if "bun" in lower_text:
                cmd = "bun test"
            elif "pnpm" in lower_text:
                cmd = "pnpm test"
            elif "yarn" in lower_text:
                cmd = "yarn test"
            else:
                cmd = "npm test"
            return {
                "runner": "Node/TS Test Runner",
                "command": cmd,
                "verification": "Run unit and integration suites to ensure 0 failing assertions."
            }
        elif lang == "python":
            cmd = "pytest -v" if "pytest" in lower_text or True else "python -m unittest"
            return {
                "runner": "pytest",
                "command": cmd,
                "verification": "Verify test suite passes with zero regressions and clean test coverage."
            }
        elif lang == "go":
            return {
                "runner": "go test",
                "command": "go test -v ./...",
                "verification": "Run all package test suites with race detection."
            }
        elif lang == "rust":
            return {
                "runner": "cargo test",
                "command": "cargo test --all",
                "verification": "Compile check and execute all unit and doc tests."
            }
        else:
            return {
                "runner": "Standard Project Test Suite",
                "command": "make test || npm test || pytest",
                "verification": "Execute repository test suite and check exit code 0."
            }

    def _generate_executive_summary(self, title: str, body: str, category: str, lang: str) -> str:
        clean_title = title.strip()
        body_lines = [l.strip() for l in (body or "").split("\n") if l.strip() and not l.startswith("#")]
        context_snippet = (" ".join(body_lines[:3]))[:300] if body_lines else "No specific reproduction details provided."
        
        type_desc = {
            "bug": "addresses an unexpected runtime failure or functional defect",
            "feature": "introduces requested capabilities or extensions",
            "refactor": "improves internal code quality, modularity, or performance",
            "documentation": "updates documentation and usage guidelines",
        }.get(category, "improves functionality")

        lang_str = f" in {lang.capitalize()}" if lang and lang != "generic" else ""
        return (
            f"This issue {type_desc}{lang_str}: \"{clean_title}\". "
            f"Reported context: {context_snippet}"
        )

    def _analyze_root_cause(self, title: str, body: str, errors: List[str], category: str) -> str:
        if errors:
            return (
                f"Identified error signals in issue report: '{errors[0]}'. "
                f"Likely root cause stems from unhandled parameter states, missing null checks, "
                f"or platform-specific execution divergences in the target module."
            )
        elif category == "bug":
            return (
                f"The issue involves inconsistent behavior during execution: '{title}'. "
                f"Investigation points to logic boundary conditions, missing validation, or mismatched assumptions in handling inputs."
            )
        else:
            return (
                f"The requirement entails updating code structure to satisfy '{title}'. "
                f"Requires implementing targeted helper functions or component adjustments while preserving existing interfaces."
            )

    def _generate_implementation_steps(
        self,
        issue_category: str,
        title: str,
        affected_files: List[str],
        test_strategy: Dict[str, Any]
    ) -> List[str]:
        target_file = affected_files[0] if affected_files else "target source file"
        steps = [
            f"Inspect `{target_file}` and trace logic related to '{title}'.",
            f"Implement surgical, minimal modifications without altering unrelated modules or interfaces.",
            f"Preserve existing comments, documentation integrity, and style conventions.",
            f"Execute test suite via `{test_strategy['command']}` and add targeted regression coverage.",
            "Perform Git diff security inspection to ensure zero credential leaks or unintended files."
        ]
        return steps

    def _generate_agent_prompt(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        title: str,
        body: str,
        plan: List[str],
        files: List[str],
        test_cmd: str
    ) -> str:
        steps_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(plan)])
        files_text = ", ".join([f"`{f}`" for f in files])
        return (
            f"I am working on GitHub issue #{issue_number} for {owner}/{repo}: '{title}'.\n\n"
            f"## Objective\n{title}\n\n"
            f"## Context & Details\n{body or 'No description provided.'}\n\n"
            f"## Target Files\n{files_text}\n\n"
            f"## Proposed Plan\n{steps_text}\n\n"
            f"## Verification Command\n`{test_cmd}`\n\n"
            f"Please help me analyze the codebase, implement the minimal surgical fix, "
            f"and verify all tests pass cleanly."
        )
