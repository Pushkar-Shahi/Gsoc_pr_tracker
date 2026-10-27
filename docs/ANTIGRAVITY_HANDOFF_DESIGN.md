# Issue-to-PR Platform: Antigravity Desktop Handoff Design

## 1. Integration Concept

Google Antigravity is a standalone desktop application. As per specification, we do NOT assume private undocumented internal APIs or pretend to control the internal conversational loop. Instead, we implement a robust desktop integration adapter:

1. Prepare the isolated Git worktree:
   - Path: `~/.issue_to_pr/workspaces/<task_id>/<repo_name>`
   - Branch: `fix/issue-<number>-<sanitized_title>`
2. Create development context files:
   - `.antigravity/BRIEF.md`: Implementation brief, constraints, test commands, acceptance criteria.
   - `.antigravity/PROMPT.txt`: Ready-to-use prompt designed to paste into Antigravity desktop chat.
3. Desktop Launch Strategy (macOS / Linux / Windows):
   - **Primary**: Attempt macOS application launch via `open -a "Antigravity" "<worktree_path>"` or `open -a "Antigravity IDE" "<worktree_path>"`.
   - **CLI Alternative**: If `agy` CLI binary is installed, invoke `agy --add-dir "<worktree_path>"`.
   - **Supported Fallback**: If desktop launch fails or application is running in an environment without direct display, the UI provides:
     - Clear one-click **"Copy Workspace Path"** button.
     - One-click **"Copy Implementation Prompt"** button formatted for Antigravity with full issue context.
     - Real-time worktree status badge (Git status, uncommitted changes, active branch).

## 2. Implementation Brief Template (`.antigravity/BRIEF.md`)

```markdown
# Antigravity Collaborative Implementation Brief

- **Issue**: [#{issue_number}] {issue_title}
- **Repository**: {owner}/{name} ({html_url})
- **Target Branch**: {default_branch}
- **Working Branch**: {branch_name}
- **Workspace Path**: {worktree_path}

## Objective & Acceptance Criteria
{issue_body}

## Prescribed Setup & Test Commands
{test_commands}

## Rules & Constraints
1. Work strictly within this worktree.
2. Do NOT touch unrelated files or configuration files like .env.
3. Follow the repository's code style and existing conventions.
4. Ensure all unit and integration tests pass before requesting validation.
```

## 3. UI Actions
- `Open in Antigravity`: Triggers the launch adapter and notifies user of result.
- `Copy Implementation Prompt`: Copies prompt into clipboard.
- `Mark Collaborative Work as Complete`: Advances task to `READY_FOR_VALIDATION`.
- `Cancel & Cleanup Workspace`: Deletes worktree safely and removes branch.
