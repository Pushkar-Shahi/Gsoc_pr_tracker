from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

# User & Organization Schemas
class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    github_id: Optional[int] = None
    github_username: str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    created_at: datetime
    updated_at: datetime


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    github_org_id: Optional[int] = None
    github_installation_id: Optional[int] = None
    is_personal: bool = False
    billing_tier: str = "starter"
    created_at: datetime
    updated_at: datetime


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    org_id: str
    role: str = "member"
    created_at: datetime
    updated_at: datetime
    user: Optional[UserRead] = None
    organization: Optional[OrganizationRead] = None


# Repository Schemas
class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner: str
    name: str
    full_name: str
    html_url: str
    default_branch: str
    primary_language: Optional[str] = None
    license_spdx: Optional[str] = None
    license_name: Optional[str] = None
    stars_count: int = 0
    open_issues_count: int = 0
    is_fork: bool = False
    is_archived: bool = False
    is_gsoc: bool = False
    gsoc_org_name: Optional[str] = None


# Issue Schemas
class IssueRankingBreakdown(BaseModel):
    skill_match: float = 0.0
    clarity_score: float = 0.0
    repo_health_score: float = 0.0
    effort_score: float = 0.0
    explanation: str = ""
    reasons: List[str] = []


class IssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    github_id: int
    issue_number: int
    title: str
    body: Optional[str] = None
    author: Optional[str] = None
    html_url: str
    state: str = "open"
    labels: List[Any] = []
    assignees: List[Any] = []
    comments_count: int = 0
    github_created_at: Optional[datetime] = None
    github_updated_at: Optional[datetime] = None
    
    is_eligible: bool = True
    ineligibility_reason: Optional[str] = None
    license_status: Optional[str] = "UNKNOWN"
    policy_status: Optional[str] = "UNKNOWN"
    
    ranking_score: Optional[float] = 50.0
    difficulty_estimate: Optional[str] = "intermediate"
    estimated_effort_hours: Optional[float] = 4.0
    ranking_breakdown: Optional[Dict[str, Any]] = None
    ai_summary: Optional[str] = None
    last_verified_at: Optional[datetime] = None

    # Availability & Linked Pull Requests
    has_open_pr: bool = False
    linked_pr_count: int = 0
    linked_prs: List[Dict[str, Any]] = []
    is_reserved: bool = False
    reservation_reason: Optional[str] = None
    availability_status: str = "AVAILABLE"  # AVAILABLE, PR_OPEN, ASSIGNED, RESERVED

    # Phase 4 Bounty Fields
    bounty_amount: Optional[float] = 0.0
    bounty_currency: Optional[str] = "USD"
    bounty_platform: Optional[str] = None
    bounty_url: Optional[str] = None
    bounty_status: Optional[str] = "NONE"
    
    repository: Optional[RepositoryRead] = None
    active_task: Optional[Dict[str, Any]] = None


class IssueListResponse(BaseModel):
    items: List[IssueRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    coverage_status: Dict[str, Any]


class IssueImportRequest(BaseModel):
    url: str = Field(..., description="GitHub Issue URL (e.g. https://github.com/owner/repo/issues/123)")


class IssueImportResponse(BaseModel):
    issue: IssueRead
    conditions_checked: Dict[str, Any]
    meets_all_conditions: bool


# Task Schemas
class TaskCreate(BaseModel):
    issue_id: str


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    issue_id: str
    workflow_state: str
    worktree_path: Optional[str] = None
    branch_name: Optional[str] = None
    remote_name: str = "origin"
    upstream_url: Optional[str] = None
    fork_owner: Optional[str] = None
    fork_url: Optional[str] = None
    implementation_brief: Optional[Dict[str, Any]] = None
    
    assignment_required: Optional[bool] = False
    draft_assignment_comment: Optional[str] = None
    user_approved_assignment: Optional[bool] = False
    assignment_posted_at: Optional[datetime] = None
    assignment_comment_id: Optional[str] = None
    maintainer_approved: Optional[bool] = False
    maintainer_notes: Optional[str] = None
    
    validation_results: Optional[Dict[str, Any]] = None
    diff_security_report: Optional[Dict[str, Any]] = None
    
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    pr_state: Optional[str] = None
    pr_ci_status: Optional[str] = None
    pr_review_status: Optional[str] = None
    pr_review_comments: Optional[List[Dict[str, Any]]] = None
    pr_merged: Optional[bool] = False
    blocked_reason: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    issue: Optional[IssueRead] = None


class PreflightResult(BaseModel):
    task_id: str
    workflow_state: str
    assignment_required: bool
    draft_comment: Optional[str] = None
    evidence: List[str]
    license_status: str
    recommendation: str


class AssignmentApprovalRequest(BaseModel):
    approved_comment: str


class AutonomousApproveRequest(BaseModel):
    custom_comment: Optional[str] = None
    auto_publish_pr: Optional[bool] = None


class ValidationRunRequest(BaseModel):
    custom_test_command: Optional[str] = None


class ValidationResult(BaseModel):
    task_id: str
    workflow_state: str
    passed: bool
    diff_security_passed: bool
    secrets_detected: List[str]
    unrelated_files: List[str]
    command_outputs: List[Dict[str, Any]]
    message: str


class PublishRequest(BaseModel):
    force_override: bool = False


class PublishResult(BaseModel):
    task_id: str
    workflow_state: str
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    success: bool
    message: str


# Discovery & Settings Schemas
class DiscoverySyncRequest(BaseModel):
    force_refresh: bool = False
    language: Optional[str] = None
    gsoc_only: bool = False


class DiscoveryStatusResponse(BaseModel):
    last_synced_at: Optional[datetime] = None
    total_issues: int = 0
    total_eligible: int = 0
    rate_limit_remaining: int = 60
    rate_limit_limit: int = 60
    rate_limit_reset: Optional[datetime] = None
    is_syncing: bool = False
    coverage_label: str = "Last synced"
    errors: List[str] = []


class PlatformSettingsRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    github_token_configured: bool = False
    github_username: Optional[str] = None
    auto_publish_pr: bool = False
    workspace_root: str
    antigravity_app_path: Optional[str] = None
    skills_profile: List[str]
    discovery_filters: Dict[str, Any]
    detected_antigravity_installed: bool = False
    detected_agy_cli: bool = False
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    custom_api_key: Optional[str] = None
    has_openai_key: bool = False
    has_anthropic_key: bool = False
    has_gemini_key: bool = False
    has_custom_key: bool = False
    enforce_shared_keys: bool = False
    preferred_ai_provider: Optional[str] = "gemini"
    org_openai_api_key: Optional[str] = None
    org_anthropic_api_key: Optional[str] = None
    org_gemini_api_key: Optional[str] = None
    org_custom_api_key: Optional[str] = None
    has_org_openai_key: bool = False
    has_org_anthropic_key: bool = False
    has_org_gemini_key: bool = False
    has_org_custom_key: bool = False


class PlatformSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    github_token: Optional[str] = None
    github_username: Optional[str] = None
    auto_publish_pr: Optional[bool] = None
    workspace_root: Optional[str] = None
    antigravity_app_path: Optional[str] = None
    skills_profile: Optional[List[str]] = None
    discovery_filters: Optional[Dict[str, Any]] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    custom_api_key: Optional[str] = None
    enforce_shared_keys: Optional[bool] = None
    preferred_ai_provider: Optional[str] = None
    scope: Optional[str] = None
    org_openai_api_key: Optional[str] = None
    org_anthropic_api_key: Optional[str] = None
    org_gemini_api_key: Optional[str] = None
    org_custom_api_key: Optional[str] = None


SettingsRead = PlatformSettingsRead
SettingsUpdate = PlatformSettingsUpdate


class RunnerRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    registration_token: str
    name: str
    os_info: Optional[str] = None


class RunnerRegisterResponse(BaseModel):
    runner_id: str
    runner_token: str


class RunnerHeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Optional[str] = "idle"
    system_stats: Optional[Dict[str, Any]] = None


class RunnerJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: str
    runner_id: Optional[str] = None
    task_id: Optional[str] = None
    job_type: str
    status: str
    payload: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class RunnerJobCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Optional[str] = "completed"
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    logs: Optional[str] = None


class RunnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: str
    name: str
    os_info: Optional[str] = None
    status: str
    system_stats: Optional[Dict[str, Any]] = None
    last_heartbeat_at: Optional[datetime] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    task_id: Optional[str] = None
    issue_id: Optional[str] = None
    action: str
    actor: str
    details: Dict[str, Any]
    created_at: datetime


# Phase 4: Bounty & Enterprise SSO Schemas
class BountyStatsResponse(BaseModel):
    total_available_usd: float
    total_bounties_count: int
    average_bounty_usd: float
    claimed_bounties_count: int
    potential_earnings_usd: float
    top_platform: str


class BountyClaimRequest(BaseModel):
    custom_notes: Optional[str] = None


class SSOConfigRead(BaseModel):
    sso_provider: Optional[str] = None
    sso_metadata_url: Optional[str] = None
    sso_entity_id: Optional[str] = None
    sso_enforced: bool = False
    sso_configured: bool = False


class SSOConfigUpdate(BaseModel):
    sso_provider: str = Field(..., description="okta, azure_ad, google, saml, oidc")
    sso_metadata_url: str
    sso_entity_id: Optional[str] = None
    sso_enforced: Optional[bool] = False


class SSOTestResponse(BaseModel):
    status: str
    message: str
    provider: str
    entity_id: Optional[str] = None
    endpoints_detected: Dict[str, str] = Field(default_factory=dict)

