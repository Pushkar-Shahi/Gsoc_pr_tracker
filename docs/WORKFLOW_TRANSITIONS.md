# Issue-to-PR Platform: Workflow State Transitions and Policy Gates

## 1. State Machine Definitions

```mermaid
stateDiagram-v2
    [*] --> DISCOVERED: Discovered via GitHub API
    DISCOVERED --> SELECTED: User Selects Issue
    SELECTED --> PREFLIGHT: Run Policy & Repo Analysis
    
    PREFLIGHT --> ASSIGNMENT_REQUEST_REQUIRED: Project requires prior assignment
    ASSIGNMENT_REQUEST_REQUIRED --> WAITING_FOR_MAINTAINER: User explicitly approves comment & posted
    WAITING_FOR_MAINTAINER --> READY_TO_WORK: Maintainer assigns / approves
    WAITING_FOR_MAINTAINER --> BLOCKED: Maintainer assigns another contributor
    
    PREFLIGHT --> READY_TO_WORK: No assignment prerequisite
    PREFLIGHT --> POLICY_REVIEW_REQUIRED: Ambiguous rules / Missing license
    PREFLIGHT --> BLOCKED: Repo archived / disabled / unpermitted
    
    POLICY_REVIEW_REQUIRED --> READY_TO_WORK: User manual policy override
    POLICY_REVIEW_REQUIRED --> BLOCKED: Unresolvable restrictions
    
    READY_TO_WORK --> WORKSPACE_PREPARED: Worktree created & branch checked out
    WORKSPACE_PREPARED --> COLLABORATIVE_WORK: Opened in Antigravity Desktop
    COLLABORATIVE_WORK --> READY_FOR_VALIDATION: User marks work complete
    READY_FOR_VALIDATION --> VALIDATING: Validation suite running
    
    VALIDATING --> VALIDATION_FAILED: Tests failed or diff contains secrets
    VALIDATION_FAILED --> COLLABORATIVE_WORK: Fixes applied in Antigravity
    
    VALIDATING --> READY_TO_PUBLISH: Tests passed + diff clean
    READY_TO_PUBLISH --> PUBLISHING: Auto-publish triggered (or manual publish)
    READY_TO_PUBLISH --> PUBLICATION_BLOCKED: Issue closed / duplicate PR detected
    
    PUBLISHING --> PR_CREATED: Pull Request created on GitHub
    PR_CREATED --> IN_REVIEW: Review comments / CI active
    IN_REVIEW --> COLLABORATIVE_WORK: Changes requested by maintainer
    IN_REVIEW --> MERGED_OR_CLOSED: PR merged or closed
    
    SELECTED --> CANCELLED: User cancels task
    WORKSPACE_PREPARED --> CANCELLED: Worktree safely cleaned up
```

## 2. Policy-Gate Matrix

| Stage Gate | Required Conditions to Advance | On Failure |
|---|---|---|
| **Preflight Gate** | Verified open issue; No existing assignees; Repo not archived; OSI-approved license detected; No duplicate open PRs. | Move to `POLICY_REVIEW_REQUIRED` with clear warning badge. |
| **Assignment Gate** | If repo specifies "comment before working", user MUST review draft comment and click "Approve & Post". API verifies assignment before branch creation. | Keep in `WAITING_FOR_MAINTAINER`. Never begin coding prematurely. |
| **Workspace Gate** | Bare clone or update succeeds; Isolated Git worktree directory created; Unique branch created matching repo convention. | Fail with disk/git error, rollback worktree. |
| **Validation Gate** | Diff security scan has ZERO secrets/unrelated files; All specified test commands return exit code 0; No test skipped disguised as passed. | Move to `VALIDATION_FAILED` with exact command output and exit codes. |
| **Publishing Gate** | `auto_publish_pr` setting enabled; Task state == `READY_TO_PUBLISH`; Remote branch pushed to fork or upstream; Target base branch verified; PR title & body include issue reference (`Fixes #...`). | Move to `PUBLICATION_BLOCKED` with detailed explanation. |
