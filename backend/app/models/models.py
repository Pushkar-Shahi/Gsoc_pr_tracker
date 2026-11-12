import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, BigInteger, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from app.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class MembershipRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    github_id = Column(BigInteger, unique=True, nullable=True, index=True)
    github_username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True, index=True)
    name = Column(String(255), nullable=True)
    avatar_url = Column(String(1024), nullable=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", primaryjoin="User.id == Task.user_id", foreign_keys="Task.user_id", back_populates="user")
    audit_logs = relationship("AuditLog", primaryjoin="User.id == AuditLog.user_id", foreign_keys="AuditLog.user_id", back_populates="user")
    settings = relationship("UserSettings", uselist=False, back_populates="user", cascade="all, delete-orphan")

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    github_org_id = Column(BigInteger, nullable=True, index=True)
    github_installation_id = Column(BigInteger, nullable=True, index=True)
    is_personal = Column(Boolean, default=False)
    billing_tier = Column(String(64), default="starter")
    sso_provider = Column(String(64), nullable=True)  # okta, azure_ad, google, saml, oidc
    sso_metadata_url = Column(String(1024), nullable=True)
    sso_entity_id = Column(String(512), nullable=True)
    sso_enforced = Column(Boolean, default=False)
    sso_config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")
    repositories = relationship("Repository", primaryjoin="Organization.id == Repository.tenant_id", foreign_keys="Repository.tenant_id", back_populates="organization", cascade="all, delete-orphan")
    tasks = relationship("Task", primaryjoin="Organization.id == Task.tenant_id", foreign_keys="Task.tenant_id", back_populates="organization", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", primaryjoin="Organization.id == AuditLog.tenant_id", foreign_keys="AuditLog.tenant_id", back_populates="organization", cascade="all, delete-orphan")
    settings = relationship("OrganizationSettings", uselist=False, back_populates="organization", cascade="all, delete-orphan")
    subscription = relationship("Subscription", uselist=False, back_populates="organization", cascade="all, delete-orphan")
    billing_customer = relationship("BillingCustomer", uselist=False, back_populates="organization", cascade="all, delete-orphan")

class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_membership_user_org"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), default=MembershipRole.MEMBER.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), index=True, nullable=True)
    user_id = Column(String(36), index=True, nullable=True)
    owner = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    full_name = Column(String(512), unique=True, nullable=False, index=True)
    html_url = Column(String(1024), nullable=False)
    default_branch = Column(String(128), default="main")
    primary_language = Column(String(128), nullable=True, index=True)
    license_spdx = Column(String(64), nullable=True)
    license_name = Column(String(255), nullable=True)
    stars_count = Column(Integer, default=0)
    open_issues_count = Column(Integer, default=0)
    is_fork = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    is_disabled = Column(Boolean, default=False)
    is_private = Column(Boolean, default=False, index=True)
    is_gsoc = Column(Boolean, default=False, index=True)
    gsoc_org_name = Column(String(255), nullable=True)
    last_inspected_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    issues = relationship("Issue", back_populates="repository", cascade="all, delete-orphan")
    organization = relationship("Organization", primaryjoin="Repository.tenant_id == Organization.id", foreign_keys=[tenant_id], back_populates="repositories")
    user = relationship("User", primaryjoin="Repository.user_id == User.id", foreign_keys=[user_id])


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("repository_id", "issue_number", name="uq_repo_issue_number"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), index=True, nullable=True)
    user_id = Column(String(36), index=True, nullable=True)
    repository_id = Column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    github_id = Column(BigInteger, unique=True, nullable=False, index=True)
    issue_number = Column(Integer, nullable=False, index=True)
    title = Column(String(1024), nullable=False)
    body = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    html_url = Column(String(1024), nullable=False)
    state = Column(String(32), default="open", index=True)
    labels = Column(JSON, default=list)
    assignees = Column(JSON, default=list)
    comments_count = Column(Integer, default=0)
    
    github_created_at = Column(DateTime, nullable=True)
    github_updated_at = Column(DateTime, nullable=True)
    github_closed_at = Column(DateTime, nullable=True)
    
    is_eligible = Column(Boolean, default=True, index=True)
    ineligibility_reason = Column(String(512), nullable=True)
    license_status = Column(String(64), default="UNKNOWN")  # VERIFIED_OSI, UNKNOWN, RESTRICTIVE, NO_LICENSE
    policy_status = Column(String(64), default="UNKNOWN")   # READY_TO_WORK, ASSIGNMENT_REQUIRED, POLICY_REVIEW_REQUIRED
    
    ranking_score = Column(Float, default=50.0, index=True)
    difficulty_estimate = Column(String(32), default="intermediate")  # beginner, intermediate, advanced
    estimated_effort_hours = Column(Float, default=4.0)
    ranking_breakdown = Column(JSON, default=dict)
    ai_summary = Column(Text, nullable=True)

    # Issue Availability & Linked Pull Request Tracking
    has_open_pr = Column(Boolean, default=False, index=True)
    linked_pr_count = Column(Integer, default=0)
    linked_prs = Column(JSON, default=list)  # List of {number, title, html_url, author, author_avatar, state, created_at}
    is_reserved = Column(Boolean, default=False, index=True)
    reservation_reason = Column(String(512), nullable=True)
    availability_status = Column(String(32), default="AVAILABLE", index=True)  # AVAILABLE, PR_OPEN, ASSIGNED, RESERVED

    # Phase 4: Bounty Platform Integrations (Polar.sh, Algora, Sponsors)
    bounty_amount = Column(Float, nullable=True, default=0.0, index=True)
    bounty_currency = Column(String(16), default="USD")
    bounty_platform = Column(String(64), nullable=True, index=True)  # polar, algora, github_sponsors
    bounty_url = Column(String(1024), nullable=True)
    bounty_status = Column(String(32), default="NONE", index=True)  # NONE, AVAILABLE, CLAIMED, MERGED_PENDING_PAYOUT, PAID
    
    last_verified_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_issues_state_eligible", "state", "is_eligible"),
        Index("idx_issues_repo_state", "repository_id", "state"),
        Index("idx_issues_availability", "availability_status", "has_open_pr"),
    )

    repository = relationship("Repository", back_populates="issues")
    tasks = relationship("Task", back_populates="issue", cascade="all, delete-orphan")
    organization = relationship("Organization", primaryjoin="Issue.tenant_id == Organization.id", foreign_keys=[tenant_id])
    user = relationship("User", primaryjoin="Issue.user_id == User.id", foreign_keys=[user_id])


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), index=True, nullable=True)
    user_id = Column(String(36), index=True, nullable=True)
    issue_id = Column(String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_state = Column(String(64), default="SELECTED", index=True)
    
    worktree_path = Column(String(1024), nullable=True)
    branch_name = Column(String(255), nullable=True)
    remote_name = Column(String(64), default="origin")
    upstream_url = Column(String(1024), nullable=True)
    fork_owner = Column(String(255), nullable=True)
    fork_url = Column(String(1024), nullable=True)
    
    implementation_brief = Column(JSON, nullable=True)
    
    # Assignment Workflow
    assignment_required = Column(Boolean, default=False)
    draft_assignment_comment = Column(Text, nullable=True)
    user_approved_assignment = Column(Boolean, default=False)
    assignment_posted_at = Column(DateTime, nullable=True)
    assignment_comment_id = Column(String(128), nullable=True)
    maintainer_approved = Column(Boolean, default=False)
    maintainer_notes = Column(Text, nullable=True)
    
    # Validation & Diff
    validation_results = Column(JSON, nullable=True)
    diff_security_report = Column(JSON, nullable=True)
    
    # Pull Request Publishing
    pr_number = Column(Integer, nullable=True)
    pr_url = Column(String(1024), nullable=True)
    pr_state = Column(String(64), nullable=True)
    pr_ci_status = Column(String(64), nullable=True)  # pending, success, failure
    pr_review_status = Column(String(64), nullable=True)  # PENDING, APPROVED, CHANGES_REQUESTED, COMMENTED
    pr_review_comments = Column(JSON, default=list)
    pr_merged = Column(Boolean, default=False)
    blocked_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_tasks_tenant_updated", "tenant_id", "updated_at"),
        Index("idx_tasks_workflow_tenant", "workflow_state", "tenant_id"),
        Index("idx_tasks_user_updated", "user_id", "updated_at"),
    )

    issue = relationship("Issue", back_populates="tasks")
    audit_logs = relationship("AuditLog", back_populates="task", cascade="all, delete-orphan")
    organization = relationship("Organization", primaryjoin="Task.tenant_id == Organization.id", foreign_keys=[tenant_id], back_populates="tasks")
    user = relationship("User", primaryjoin="Task.user_id == User.id", foreign_keys=[user_id], back_populates="tasks")


class DiscoveryCheckpoint(Base):
    __tablename__ = "discovery_checkpoints"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    query_key = Column(String(255), unique=True, nullable=False, index=True)
    last_since = Column(DateTime, nullable=True)
    last_page = Column(Integer, default=1)
    items_synced = Column(Integer, default=0)
    is_complete = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), index=True, nullable=True)
    user_id = Column(String(36), index=True, nullable=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    issue_id = Column(String(36), ForeignKey("issues.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(128), nullable=False, index=True)
    actor = Column(String(64), default="USER")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    task = relationship("Task", back_populates="audit_logs")
    organization = relationship("Organization", primaryjoin="AuditLog.tenant_id == Organization.id", foreign_keys=[tenant_id], back_populates="audit_logs")
    user = relationship("User", primaryjoin="AuditLog.user_id == User.id", foreign_keys=[user_id], back_populates="audit_logs")


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id = Column(Integer, primary_key=True, default=1)
    github_token = Column(String(255), nullable=True)
    github_username = Column(String(128), nullable=True)
    auto_publish_pr = Column(Boolean, default=False)
    workspace_root = Column(String(1024), nullable=True)
    antigravity_app_path = Column(String(1024), nullable=True)
    skills_profile = Column(JSON, default=list)
    discovery_filters = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    openai_api_key_encrypted = Column(Text, nullable=True)
    anthropic_api_key_encrypted = Column(Text, nullable=True)
    gemini_api_key_encrypted = Column(Text, nullable=True)
    custom_api_key_encrypted = Column(Text, nullable=True)
    custom_endpoint = Column(String(1024), nullable=True)
    preferred_ai_provider = Column(String(64), default="gemini")
    skills_profile = Column(JSON, default=list)
    auto_publish_pr = Column(Boolean, default=False)
    workspace_root = Column(String(1024), nullable=True)
    antigravity_app_path = Column(String(1024), nullable=True)
    discovery_filters = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="settings")


class OrganizationSettings(Base):
    __tablename__ = "organization_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    openai_api_key_encrypted = Column(Text, nullable=True)
    anthropic_api_key_encrypted = Column(Text, nullable=True)
    gemini_api_key_encrypted = Column(Text, nullable=True)
    custom_api_key_encrypted = Column(Text, nullable=True)
    custom_endpoint = Column(String(1024), nullable=True)
    enforce_shared_keys = Column(Boolean, default=False)
    billing_tier = Column(String(64), default="starter")
    triage_policy = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="settings")


class Runner(Base):
    __tablename__ = "runners"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), index=True, nullable=True)
    user_id = Column(String(36), index=True, nullable=True)
    name = Column(String(255), nullable=False)
    os_info = Column(String(255), nullable=True)
    status = Column(String(32), default="idle")
    runner_token = Column(String(255), unique=True, nullable=True, index=True)
    token_hash = Column(String(255), unique=True, nullable=True, index=True)
    registration_token = Column(Text, nullable=True)
    system_stats = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    last_heartbeat_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    jobs = relationship("RunnerJob", back_populates="runner", cascade="all, delete-orphan")


class RunnerJob(Base):
    __tablename__ = "runner_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), index=True, nullable=True)
    runner_id = Column(String(36), ForeignKey("runners.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id = Column(String(36), nullable=True, index=True)
    job_type = Column(String(64), nullable=False)
    status = Column(String(32), default="queued")
    priority = Column(Integer, default=10, index=True)
    payload = Column(JSON, default=dict)
    result = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runner = relationship("Runner", back_populates="jobs")


class BillingCustomer(Base):
    __tablename__ = "billing_customers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    stripe_customer_id = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="billing_customer")
    user = relationship("User")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), unique=True, nullable=False, index=True)
    stripe_customer_id = Column(String(255), nullable=False, index=True)
    stripe_price_id = Column(String(255), nullable=True)
    plan_tier = Column(String(64), default="pro", nullable=False)  # starter, pro, team, enterprise
    status = Column(String(64), default="active", nullable=False)  # active, trialing, past_due, canceled
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    quantity = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="subscription")
    user = relationship("User")


class UsageMeter(Base):
    __tablename__ = "usage_meters"
    __table_args__ = (
        UniqueConstraint("tenant_id", "metric_name", "period_start", name="uq_tenant_metric_period"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_name = Column(String(64), nullable=False, index=True)  # tasks_created, compute_minutes
    period_start = Column(DateTime, nullable=False, index=True)
    period_end = Column(DateTime, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    limit_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization")


class UpiPaymentRequest(Base):
    __tablename__ = "upi_payment_requests"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    payer_username = Column(String(255), nullable=True)
    payer_email = Column(String(255), nullable=True)
    payment_purpose = Column(String(32), default="plan", nullable=False)  # plan, support
    plan_tier = Column(String(32), nullable=True)  # pro, team
    billing_cycle = Column(String(16), nullable=True)  # monthly, annual, one_time
    amount_inr = Column(Integer, nullable=False)
    upi_vpa = Column(String(255), nullable=False)
    utr_number = Column(String(64), nullable=False, index=True)
    payer_upi_id = Column(String(255), nullable=True)
    note = Column(String(512), nullable=True)
    status = Column(String(32), default="pending", nullable=False, index=True)  # pending, approved, rejected
    admin_note = Column(String(512), nullable=True)
    reviewed_by_user_id = Column(String(36), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization")
    user = relationship("User")


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    repo_full_name = Column(String(512), nullable=False, index=True)
    webhook_secret = Column(String(255), nullable=False)
    events = Column(JSON, default=lambda: ["issues", "pull_request", "pull_request_review"])
    is_active = Column(Boolean, default=True, nullable=False)
    deliveries_count = Column(Integer, default=0, nullable=False)
    last_delivery_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization")
    user = relationship("User")


