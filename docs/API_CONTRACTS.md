# Issue-to-PR Platform: API Contracts and Typed Data Models

## 1. REST Endpoints

### Issues & Discovery
- `GET /api/v1/issues`
  - Query parameters: `page`, `page_size`, `query`, `language`, `repository`, `difficulty`, `state`, `min_score`, `only_eligible`, `sort_by` (`rank`, `created_at`, `effort`, `stars`)
  - Returns paginated list of issues with explainable ranking breakdown, license status, and repository metadata.
- `GET /api/v1/issues/{issue_id}`
  - Returns detailed issue record including full markdown body, repository rules, verified GitHub data vs AI analysis, and existing task if any.
- `POST /api/v1/discovery/sync`
  - Body: `{ force_refresh: boolean, query_partition?: string }`
  - Triggers asynchronous discovery run; returns `{ job_id, status, coverage_summary }`.
- `GET /api/v1/discovery/status`
  - Returns last sync timestamp, total eligible issues, current rate limits, and any recent API errors.

### Tasks & State Machine
- `POST /api/v1/tasks/select`
  - Body: `{ issue_id: string }`
  - Transitions issue from `DISCOVERED` to `SELECTED`, initiates preflight policy check.
- `POST /api/v1/tasks/{task_id}/preflight`
  - Re-evaluates contribution policy, inspects `CONTRIBUTING.md`, determines if assignment request is needed.
- `POST /api/v1/tasks/{task_id}/assignment/approve`
  - Body: `{ approved_comment: string }`
  - Submits the approved comment to GitHub via authorized API, moves task to `WAITING_FOR_MAINTAINER`.
- `POST /api/v1/tasks/{task_id}/assignment/recheck`
  - Checks if issue has been assigned or maintainer replied positively.
- `POST /api/v1/tasks/{task_id}/workspace/prepare`
  - Clones/updates repo, creates isolated worktree and branch, generates `.antigravity/BRIEF.md`.
- `POST /api/v1/tasks/{task_id}/antigravity/open`
  - Launches desktop app or returns fallback prompt with workspace path.
- `POST /api/v1/tasks/{task_id}/validation/run`
  - Body: `{ custom_test_command?: string }`
  - Scans git diff for secrets/unrelated files, executes test suite, records outputs.
- `POST /api/v1/tasks/{task_id}/publish`
  - Verifies all policy gates and publishes pull request (via direct push or fork workflow).
- `POST /api/v1/tasks/{task_id}/cancel`
  - Safely deletes Git worktree and marks task as cancelled.

### Settings & Audit
- `GET /api/v1/settings`
  - Retrieves configuration (skills profile, discovery filters, auto-publish status, workspace paths, Antigravity path). Sensitive tokens masked (`ghp_***`).
- `PUT /api/v1/settings`
  - Updates configuration.
- `GET /api/v1/audit-logs`
  - Returns immutable activity history with filtering by task or action.
