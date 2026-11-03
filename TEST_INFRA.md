# Test Infrastructure Specification: Phase 1 (Multi-Tenancy & GitHub App Foundation)

## 1. Test Philosophy & Principles

The Phase 1 automated test suite is built on four core tenets:

1. **Opaque-Box Requirement-Driven Testing**: Tests validate platform behavior against functional requirements defined in `ORIGINAL_REQUEST.md`, `PROJECT.md`, and `scale_and_monetize_plan.md`. Tests interact solely with public HTTP endpoints (`/api/v1/*`), database entities, and cryptographic/service contracts without asserting on internal implementation details.
2. **Progressive Testability & Graceful Gaps**: Tests are partitioned into clear architectural tiers (Features, Boundaries, Combinations, Scenarios). They execute against the live FastAPI application and PostgreSQL database (`issuetopr_test`), pinpointing exact compliance or identifying unfulfilled requirements for implementing agents.
3. **Strict Isolation & Zero Cross-Contamination**: Each test creates distinct, securely scoped test fixtures (unique tenant IDs, user identities, mock runners, and repository contexts) to ensure tests never depend on execution order or leak state into peer tests.
4. **Adversarial Hardening**: The suite includes boundary, stress, and security tests: cross-tenant IDOR tampering, forged HMAC-SHA256 signatures, malformed tokens, expired OAuth states, encrypted key sanitization, and offline runner heartbeats.
5. **Zero Implementation Code Tampering**: As enforced by the test writer boundary, all testing infrastructure, mocks, and test suites reside exclusively within `TEST_INFRA.md`, `TEST_READY.md`, and `tests/e2e/`. Application code under `backend/app/` is never modified by the test writer.

---

## 2. Feature Inventory (F1 – F5)

| Code | Feature Area | Key Requirements | Interfaces & Endpoints |
| :--- | :--- | :--- | :--- |
| **F1** | **Tenant Models & Data Isolation** | Multi-tenant schema (`User`, `Organization`, `Membership`); Foreign keys on `tasks`, `issues`, `repositories`, `audit_logs`; Query scoping & cross-tenant invisibility; Multi-tenant RBAC (`owner`, `admin`, `member`). | `app.models.models`<br>`GET /api/v1/tasks`<br>`GET /api/v1/tasks/{id}`<br>`GET /api/v1/audit-logs`<br>`DELETE /api/v1/audit-logs`<br>`app.core.tenant.get_current_tenant` |
| **F2** | **GitHub OAuth 2.0 & Session Auth** | OAuth authorization code flow; CSRF state validation; Code exchange & profile upsert; HMAC-SHA256 session token generation (`claims` payload); Current user profile endpoint; Backward compatibility with legacy tokens. | `GET /api/v1/auth/github/login`<br>`GET /api/v1/auth/github/callback`<br>`GET /api/v1/auth/me`<br>`app.core.security.generate_session_token`<br>`app.core.security.decode_session_token` |
| **F3** | **GitHub App Webhooks & HMAC Ingestion** | HMAC-SHA256 verification via `X-Hub-Signature-256`; Auth middleware exemption; Event dispatching (`ping`, `issues`, `pull_request`, `pull_request_review`, `check_run`); State synchronization (issue closed -> task BLOCKED, PR merged -> task MERGED_OR_CLOSED). | `POST /api/v1/webhooks/github`<br>`app.core.security.verify_github_webhook_signature`<br>`app.services.webhook_service.process_github_webhook_event` |
| **F4** | **Per-Tenant Settings & BYOK Keys** | `UserSettings` & `OrganizationSettings`; Symmetric encryption at rest (AES-256); Masked secret previews (`sk-...a1b2`); Hierarchical key resolver (User -> Org -> Environment fallback); Key leakage prevention. | `GET /api/v1/settings`<br>`PUT /api/v1/settings`<br>`app.core.crypto.encrypt_secret`<br>`app.core.crypto.decrypt_secret`<br>`app.services.settings_resolver.get_effective_ai_key` |
| **F5** | **Hybrid Runner Foundation** | `Runner` & `RunnerJob` entities; Runner pairing via temporary registration tokens; Persistent revokable runner tokens (`rnt_...`); Heartbeat reporting & offline timeout detection; Long-poll job dispatch and completion. | `POST /api/v1/runners/register`<br>`POST /api/v1/runners/{id}/heartbeat`<br>`GET /api/v1/runners/jobs/poll`<br>`POST /api/v1/runners/jobs/{id}/complete`<br>`DELETE /api/v1/runners/{id}` |

---

## 3. Directory Layout

```
/Users/shahi/Desktop/PROJECT/issue-to-pr-platform/
├── TEST_INFRA.md                       <- This infrastructure specification
├── TEST_READY.md                       <- Readiness summary and execution commands
├── pytest.ini                          <- Root pytest configuration
├── tests/
│   ├── conftest.py                     <- Global pytest configuration & DB engine init
│   ├── test_*.py                       <- Existing unit and integration test suite (18 tests)
│   └── e2e/                            <- Phase 1 Opaque-Box E2E Test Suite
│       ├── __init__.py
│       ├── conftest.py                 <- E2E fixtures: Async client, mock OAuth, mock webhooks, test tenants
│       ├── test_tier1_features.py      <- Tier 1: Core Feature Coverage (>=25 tests: F1-F5 >=5 each)
│       ├── test_tier2_boundaries.py    <- Tier 2: Boundary & Corner Cases (>=25 tests: F1-F5 >=5 each)
│       ├── test_tier3_combinations.py  <- Tier 3: Cross-Feature Combinations (>=10 tests)
│       └── test_tier4_scenarios.py     <- Tier 4: Real-World End-to-End User Workflows (>=5 tests)
```

---

## 4. Test Suite Structure & Tier Definitions

### Tier 1: Core Feature Coverage (`tests/e2e/test_tier1_features.py`)
- **Objective**: Validate the primary happy paths for each of the 5 features.
- **Minimum Test Count**: 25 (>=5 tests per feature).
- **Scope**:
  - **F1**: User/Organization/Membership creation; FK linkage on tasks and issues; tenant-scoped task listing; audit log scoping.
  - **F2**: GitHub login URL structure and state generation; JSON login response; OAuth callback code exchange & upsert; `/auth/me` with session claims; legacy token backward compatibility.
  - **F3**: Webhook ping verification; `issues.opened` ingestion; `issues.closed` active task blocking; `pull_request.closed` (merged) task completion; `pull_request_review` changes requested.
  - **F4**: User BYOK key encrypted storage; masked preview in settings response; User > Org key resolution precedence; Org > Env key resolution precedence; Organization settings persistence.
  - **F5**: Runner pairing & `rnt_...` token generation; heartbeat updates; job polling queue; job completion lifecycle; runner list scoped to tenant.

### Tier 2: Boundary & Corner Cases (`tests/e2e/test_tier2_boundaries.py`)
- **Objective**: Rigorously test error handling, invalid inputs, security barriers, and edge cases.
- **Minimum Test Count**: 25 (>=5 tests per feature).
- **Scope**:
  - **F1 Boundaries**: Cross-tenant IDOR read/update/delete rejection (HTTP 403/404); audit log clearing isolation; invalid `X-Organization-Id` rejection; unauthenticated requests.
  - **F2 Boundaries**: OAuth callback with missing/empty code or state; expired/forged state; expired session token rejection; tampered HMAC signature on token; malformed Authorization header.
  - **F3 Boundaries**: Missing `X-Hub-Signature-256` (HTTP 401); forged/invalid HMAC signature (HTTP 401); malformed signature format (HTTP 401); empty request body; invalid JSON payload.
  - **F4 Boundaries**: Malformed/corrupted encrypted secret decryption handling; empty or whitespace API key handling; cross-tenant settings IDOR; unknown AI provider resolution; unauthenticated settings modification.
  - **F5 Boundaries**: Invalid/expired runner registration token; heartbeat to nonexistent runner ID; invalid runner Bearer token; runner offline status detection after heartbeat timeout; cross-tenant runner job poll prevention.

### Tier 3: Cross-Feature Combinations (`tests/e2e/test_tier3_combinations.py`)
- **Objective**: Exercise multi-step interactions across two or more subsystems.
- **Minimum Test Count**: 10 tests.
- **Scope**:
  1. OAuth login -> BYOK settings save -> task creation -> webhook status update -> hybrid runner job poll.
  2. OAuth signup -> Org creation -> BYOK set -> Runner paired -> Heartbeat maintained.
  3. Webhook issue ingested -> Task selected by Tenant A -> Tenant B verified isolated -> Runner polls job for Tenant A.
  4. User sets BYOK key -> Organization overrides key -> Enforce shared keys toggle -> Effective key resolution.
  5. Runner registers -> Picks up task workspace prepare -> Reports logs -> Completes -> Task advances state.
  6. Webhook PR changes requested -> Task moved back to `COLLABORATIVE_WORK` -> Runner receives rework job.
  7. Webhook PR merged -> Task marked `MERGED_OR_CLOSED` -> Runner job finished -> Audit log stamped with tenant.
  8. Multi-tenant concurrent task creation on identical public issue -> Independent state machines.
  9. OAuth session token renewal / rotation with BYOK settings persistence.
  10. Tenant member role escalation attempt -> Non-admin blocked from modifying Organization BYOK settings.

### Tier 4: Real-World End-to-End Scenarios (`tests/e2e/test_tier4_scenarios.py`)
- **Objective**: Simulate complete real-world user journeys for open-source bounty hunters, contributors, and maintainers.
- **Minimum Test Count**: 5 tests.
- **Scope**:
  1. **Bounty Hunter Journey**: OAuth login -> Save OpenAI BYOK key -> Discover high-bounty issue via webhook -> Pair local M3 Mac runner -> Prepare workspace.
  2. **Competing Bounty Hunters**: Two developers (Alice and Bob) from separate tenants work on the same issue independently with different BYOK keys (Gemini vs Anthropic) with zero leakage.
  3. **Team Collaborative Triage**: GitHub App installs on team repo -> Ingests webhook -> Dispatches validation test run to hybrid runner -> Webhook review triggers automated update.
  4. **Upstream Disruption & Graceful Recovery**: Developer working on active task -> Upstream maintainer closes issue on GitHub -> Webhook arrives -> Task is cleanly blocked, runner job updated, audit log logged.
  5. **Full Lifecycle to PR Merge**: OAuth registration -> BYOK configuration -> Issue ingestion -> Task selection -> Runner job validation -> PR publishing simulation -> Webhook PR merge -> Final audit log verification.

---

## 5. Test Runner Invocation

All tests run using the project virtual environment Python and pytest configuration:

```bash
# Run all E2E tests
backend/.venv/bin/pytest tests/e2e/ -v

# Run individual tiers
backend/.venv/bin/pytest tests/e2e/test_tier1_features.py -v
backend/.venv/bin/pytest tests/e2e/test_tier2_boundaries.py -v
backend/.venv/bin/pytest tests/e2e/test_tier3_combinations.py -v
backend/.venv/bin/pytest tests/e2e/test_tier4_scenarios.py -v

# Run both existing unit tests and new E2E tests
backend/.venv/bin/pytest tests/ -v
```

---

## 6. Coverage & Quality Thresholds

- **Total E2E Test Cases**: >= 65 tests (Tier 1: >=25, Tier 2: >=25, Tier 3: >=10, Tier 4: >=5).
- **Zero Regressions**: All 18 existing unit/integration tests in `tests/` must continue to pass.
- **Strict Tenant Isolation**: 100% of multi-tenant read/write operations must assert HTTP 403, 404, or empty result sets when queried across tenant boundaries.
- **Security Verification**: 100% of webhook calls without valid `X-Hub-Signature-256` HMAC-SHA256 signatures must be rejected with HTTP 401.
