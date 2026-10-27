# Issue-to-PR Platform: Database Schema and Migration Design

## 1. Schema Diagram

```mermaid
erDiagram
    REPOSITORIES ||--o{ ISSUES : contains
    ISSUES ||--o{ TASKS : spawns
    TASKS ||--o{ AUDIT_LOGS : records
    DISCOVERY_CHECKPOINTS {
        string query_key PK
        timestamp last_since
        int last_page
        int items_synced
        boolean is_complete
        string error_message
    }
    REPOSITORIES {
        uuid id PK
        string owner
        string name
        string full_name UK
        string html_url
        string default_branch
        string primary_language
        string license_spdx
        string license_name
        int stars_count
        boolean is_archived
        boolean is_fork
        timestamp last_inspected_at
    }
    ISSUES {
        uuid id PK
        uuid repository_id FK
        bigint github_id UK
        int issue_number
        string title
        text body
        string author
        string html_url
        string state
        jsonb labels
        int comments_count
        boolean is_eligible
        string ineligibility_reason
        string license_status
        string policy_status
        float ranking_score
        string difficulty_estimate
        float estimated_effort_hours
        jsonb ranking_breakdown
        text ai_summary
        timestamp last_verified_at
    }
    TASKS {
        uuid id PK
        uuid issue_id FK
        string workflow_state
        string worktree_path
        string branch_name
        string fork_owner
        string fork_url
        boolean assignment_required
        string draft_assignment_comment
        boolean user_approved_assignment
        timestamp assignment_posted_at
        string assignment_comment_id
        boolean maintainer_approved
        jsonb validation_results
        jsonb diff_security_report
        int pr_number
        string pr_url
        string pr_state
        string pr_ci_status
        timestamp created_at
        timestamp updated_at
    }
    AUDIT_LOGS {
        uuid id PK
        uuid task_id FK
        uuid issue_id FK
        string action
        string actor
        jsonb details
        timestamp created_at
    }
    PLATFORM_SETTINGS {
        int id PK
        string github_token
        boolean auto_publish_pr
        string workspace_root
        string antigravity_app_path
        jsonb skills_profile
        jsonb discovery_filters
        timestamp updated_at
    }
```

## 2. Constraints and Invariants
1. **Uniqueness**:
   - `repositories(full_name)` must be unique (`owner/name`).
   - `issues(repository_id, issue_number)` has a composite unique constraint to prevent duplicates.
   - `tasks(issue_id)` enforces a single active task per issue.
2. **Referential Integrity**:
   - Cascading deletes on non-critical metadata, strict restrict on active tasks with open worktrees.
3. **Audit Immutability**:
   - `audit_logs` records are append-only. No updates or deletions are permitted through application APIs.
