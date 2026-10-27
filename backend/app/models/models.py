import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, BigInteger, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(String(36), primary_key=True, default=generate_uuid)
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
    is_gsoc = Column(Boolean, default=False, index=True)
    gsoc_org_name = Column(String(255), nullable=True)
    last_inspected_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    issues = relationship("Issue", back_populates="repository", cascade="all, delete-orphan")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("repository_id", "issue_number", name="uq_repo_issue_number"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
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
    
    last_verified_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    repository = relationship("Repository", back_populates="issues")
    tasks = relationship("Task", back_populates="issue", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
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

    issue = relationship("Issue", back_populates="tasks")
    audit_logs = relationship("AuditLog", back_populates="task", cascade="all, delete-orphan")


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
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    issue_id = Column(String(36), ForeignKey("issues.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(128), nullable=False, index=True)
    actor = Column(String(64), default="USER")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    task = relationship("Task", back_populates="audit_logs")


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
