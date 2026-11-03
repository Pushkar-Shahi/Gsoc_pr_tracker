# Project: Issue-to-PR Platform — Phase 1 (Multi-Tenancy & GitHub App Foundation)

## Architecture
The platform is transitioning from a single-user local tool to a multi-tenant, event-driven hybrid architecture:
- **Tenant & Identity Layer**: Multi-tenant schema with `User`, `Organization`, and `Membership` entities. Tasks, repositories, issues, and audit logs are scoped by tenant identifiers (`tenant_id` referencing `Organization.id`, `user_id` referencing `User.id`).
- **Authentication & Sessions**: GitHub OAuth 2.0 flow (`/api/v1/auth/github/login`, `/callback`) generating tamper-proof HMAC-SHA256 session tokens with tenant claims, alongside full backward compatibility for local development and existing test tokens.
- **Event-Driven Ingestion**: GitHub App webhook endpoint (`/api/v1/webhooks/github`) protected by strict HMAC SHA-256 signature verification (`X-Hub-Signature-256`), routing issue and PR events directly into platform state without reliance on continuous polling.
- **Per-Tenant Settings & BYOK**: `UserSettings` and `OrganizationSettings` with symmetric encryption (AES-256) for Bring-Your-Own-Key LLMs (OpenAI, Anthropic, Gemini, custom endpoints), masked API previews, and prioritized key resolution.
- **Hybrid Local Runner**: Distributed runner coordination enabling developer machines to securely pair (`rnt_...` runner tokens), report heartbeats, and pull/stream task execution jobs (worktree creation, local Antigravity launching, test validation) while keeping code on the developer's hardware.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | R1: Multi-Tenant Schema Models | Add `User`, `Organization`, `Membership` models to `app/models/models.py` | M1 | ORIGINAL_REQUEST §R1 |
| 2 | R1: Tenant ID Foreign Keys | Associate `tenant_id` and `user_id` with `repositories`, `issues`, `tasks`, and `audit_logs` | M1 | ORIGINAL_REQUEST §R1 |
| 3 | R1: Database Migration & Seeding | Extend `create_tables()` with non-destructive ALTER statements and default tenant seeding | M1 | ORIGINAL_REQUEST §R1 |
| 4 | R1: Tenant Context Dependency | Provide `get_current_tenant` FastAPI dependency in `app/core/tenant.py` | M1 | ORIGINAL_REQUEST §R1 |
| 5 | R1: Query Isolation & Scoping | Enforce strict tenant filtering across tasks, issues, audit logs, and settings APIs | M1 | ORIGINAL_REQUEST §R1 |
| 6 | R2: Session Token Claims & Decoding | Update `generate_session_token`, `decode_session_token` in `app/core/security.py` | M2 | ORIGINAL_REQUEST §R2 |
| 7 | R2: GitHub OAuth 2.0 Flow | Implement `/api/v1/auth/github/login` and `/callback` with CSRF state validation and token exchange | M2 | ORIGINAL_REQUEST §R2 |
| 8 | R2: Current User Endpoint & Dep | Update `/api/v1/auth/me` and add `get_current_user` dependency with legacy token compatibility | M2 | ORIGINAL_REQUEST §R2 |
| 9 | R3: Webhook HMAC Verification | Implement `verify_github_webhook_signature` (`X-Hub-Signature-256`) in `app/core/security.py` | M3 | ORIGINAL_REQUEST §R3 |
| 10 | R3: GitHub App Webhook Endpoint | Implement `/api/v1/webhooks/github`, rejecting invalid/missing signatures with HTTP 401 | M3 | ORIGINAL_REQUEST §R3 |
| 11 | R3: Webhook Event Dispatcher | Process `issues`, `pull_request`, `pull_request_review`, and `check_run` events into platform tasks | M3 | ORIGINAL_REQUEST §R3 |
| 12 | R4: Per-Tenant Settings Models | Implement `UserSettings` and `OrganizationSettings` models | M4 | ORIGINAL_REQUEST §R4 |
| 13 | R4: BYOK Cryptographic Storage | Symmetrically encrypt LLM keys at rest (AES-256) and return masked previews | M4 | ORIGINAL_REQUEST §R4 |
| 14 | R4: Settings API Migration | Migrate `/api/v1/settings` to per-user and per-organization settings with key resolver | M4 | ORIGINAL_REQUEST §R4 |
| 15 | R5: Hybrid Runner Foundation | Implement `Runner` & `RunnerJob` models, registration, heartbeat, and job polling endpoints | M4 | ORIGINAL_REQUEST §R5 |
| 16 | Verification: Zero Test Regressions | Verify all 18 existing pytest test cases continue passing | M5 | ORIGINAL_REQUEST §Acceptance |
| 17 | Verification: Tenant Isolation Tests | Verify tenant data isolation (cross-tenant task/issue/audit read, update, delete rejection) | M5 | ORIGINAL_REQUEST §Acceptance |
| 18 | Verification: OAuth & Webhook Tests | Verify OAuth login/callback and HMAC-SHA256 signature verification rejection & acceptance | M5 | ORIGINAL_REQUEST §Acceptance |
| 19 | Verification: BYOK Key Security Tests | Verify per-tenant key storage and isolation without cross-tenant key leakage | M5 | ORIGINAL_REQUEST §Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Multi-Tenant Data Models & Isolation | `User`, `Organization`, `Membership` models, foreign keys, migrations, tenant context, query scoping | none | IN_PROGRESS (conv: 0ecdcecc-fbac-40ff-ba4f-742b53e7ba89) |
| M2 | GitHub OAuth 2.0 & Session Auth | Session claims, `/api/v1/auth/github/login`, `/callback`, `/me`, `get_current_user`, middleware update | M1 | PLANNED |
| M3 | GitHub App Webhooks & HMAC Ingestion | `verify_github_webhook_signature`, `/api/v1/webhooks/github`, webhook event handlers, middleware exemption | M1 | PLANNED |
| M4 | Per-Tenant BYOK Settings & Hybrid Runner | `UserSettings`, `OrganizationSettings`, AES-256 crypto, settings resolver, `/runners` endpoints | M1, M2 | PLANNED |
| M5 | Final Milestone: 100% E2E Pass & Hardening | Pass 100% of E2E tests (Tiers 1-4) published by E2E track, adversarial hardening (Tier 5) | M1, M2, M3, M4 | PLANNED |

## Interface Contracts

### `app/core/tenant.py` ↔ API Routers (`tasks.py`, `issues.py`, `settings.py`, `audit.py`)
- Function: `async def get_current_tenant(authorization: Optional[str] = Header(None), x_organization_id: Optional[str] = Header(None), db: AsyncSession = Depends(get_db)) -> TenantContext`
- Return type: `TenantContext(user: User, organization: Organization, membership: Membership, role: str)`
- Error behavior: HTTP 401 if token missing or invalid; HTTP 403 if user not member of requested organization.

### `app/core/security.py` ↔ Auth Router (`auth.py`) & Webhook Router (`webhooks.py`)
- `generate_session_token(subject: str = "user", claims: Optional[Dict[str, Any]] = None) -> str`
- `decode_session_token(token: str) -> Optional[Dict[str, Any]]`
- `verify_session_token(token: str) -> bool` (backward compatible)
- `verify_github_webhook_signature(raw_body: bytes, signature_header: Optional[str], secret: Optional[str]) -> bool`

### `app/services/settings_resolver.py` ↔ AI Services & Settings Router
- `async def get_effective_ai_key(db: AsyncSession, ctx: TenantContext, provider: str = "gemini") -> Optional[str]`
  Priority: UserSettings -> OrganizationSettings -> os.getenv() -> None

### `app/api/v1/runners.py` ↔ Hybrid Local Runner Daemon
- `POST /api/v1/runners/register` (body: `{"registration_token": str, "name": str, "os_info": str}`) -> `{"runner_id": str, "runner_token": str}`
- `POST /api/v1/runners/{runner_id}/heartbeat` (body: `{"status": str, "system_stats": dict}`) -> `{"status": "ok"}`
- `GET /api/v1/runners/jobs/poll` -> `RunnerJobRead` or 204 No Content

## Code Layout
- `backend/app/models/models.py`: All database entities (`User`, `Organization`, `Membership`, `UserSettings`, `OrganizationSettings`, `Runner`, `RunnerJob`, `Repository`, `Issue`, `Task`, `AuditLog`, `PlatformSettings`).
- `backend/app/core/config.py`: Settings (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`, `GITHUB_WEBHOOK_SECRET`, `FRONTEND_AUTH_CALLBACK_URL`).
- `backend/app/core/security.py`: Token signing, decoding, webhook HMAC verification.
- `backend/app/core/crypto.py`: AES-256 symmetric encryption/decryption for BYOK keys.
- `backend/app/core/tenant.py`: `TenantContext` dataclass and `get_current_tenant` dependency.
- `backend/app/db/database.py`: Async engine, table creation, and non-destructive column migrations.
- `backend/app/schemas/schemas.py`: Pydantic request/response schemas for Auth, Settings, Runners, Tasks, Issues.
- `backend/app/api/v1/auth.py`: OAuth login/callback, password login, biometric endpoints, `/me`.
- `backend/app/api/v1/webhooks.py`: GitHub App webhook ingestion endpoint.
- `backend/app/api/v1/settings.py`: Per-user & per-organization settings endpoints.
- `backend/app/api/v1/runners.py`: Hybrid runner registration, heartbeat, job polling endpoints.
- `backend/app/services/webhook_service.py`: Webhook event routing and state synchronization.
- `backend/app/services/settings_resolver.py`: BYOK key priority resolution.
- `tests/`: Existing unit/integration tests and new multi-tenant test suites.
- `tests/e2e/`: Requirement-driven E2E test suites (Tiers 1-4).
