# Issue-to-PR Platform: Test Plan and Measurable Acceptance Criteria

## 1. Test Strategy

| Test Suite | Focus | Method |
|---|---|---|
| **Unit Tests** | Explainable ranking calculations, eligibility filters, policy classification, diff secret scanner, PR body generator. | Pytest with parameterized cases |
| **Integration Tests** | Database persistence, state machine transitions, worktree lifecycle, GitHub API client mocking. | Pytest with PostgreSQL / SQLite test database |
| **API End-to-End Tests** | Full workflow lifecycle: discover -> select -> preflight -> assign -> worktree -> validate -> publish. | FastAPI TestClient |
| **Security Tests** | Diff scanner detecting AWS keys, RSA private keys, `.env`, tokens; path traversal resistance. | Explicit test fixtures with hostile payloads |
| **UI Acceptance Tests** | Dashboard rendering, search/filters, assignment approval modal, validation status, settings persistence. | React testing and browser verification |

## 2. Measurable Acceptance Criteria by Milestone

### Phase 1: Issue Discovery Dashboard
- [x] Unassigned, open, non-archived public issues fetched and persisted in PostgreSQL.
- [x] Composite uniqueness constraint prevents duplicate issues across runs.
- [x] Ranking algorithm computes explainable score components (match, clarity, effort, health).
- [x] All discovered eligible issues remain available regardless of score.
- [x] Dashboard supports live search, language/repository/difficulty filters, and manual sync.

### Phase 2: Policy and Assignment Workflow
- [x] Preflight inspects `CONTRIBUTING.md` and repository guidelines.
- [x] Classifies into `READY_TO_WORK`, `ASSIGNMENT_REQUEST_REQUIRED`, `WAITING_FOR_MAINTAINER`, `POLICY_REVIEW_REQUIRED`, `BLOCKED`.
- [x] Draft assignment request shown in dashboard UI.
- [x] Requires explicit user action before any comment can be posted to GitHub.
- [x] Task blocked until assignment confirmation is verified.

### Phase 3: Collaborative Antigravity Integration
- [x] Safe clone & dedicated Git worktree created without affecting existing repositories.
- [x] Dedicated branch created following naming conventions.
- [x] Context file `.antigravity/BRIEF.md` and copyable prompt generated.
- [x] Antigravity desktop launch adapter detects macOS app / CLI with UI fallback.
- [x] Diff inspection detects uncommitted changes, untracked files, and high-entropy secrets.
- [x] Validation runner executes commands, records exit codes, and blocks on failures.

### Phase 4: Automated PR Publishing
- [x] Auto-publish setting toggle required.
- [x] Validates all policy gates before publishing.
- [x] Fork created or reused when upstream write access is unavailable.
- [x] Branch pushed to remote; PR opened with standard template referencing issue (`Fixes #...`).
- [x] No duplicate PRs created.
- [x] Explicit prohibition against automatic merging or deployment enforced.

### Phase 5: Reliability & Refinement
- [x] Rate limit handling and exponential backoff implemented.
- [x] Tasks recoverable across service restarts.
- [x] Full audit log of all system transitions and external actions.
