export interface Repository {
  id: string;
  owner: string;
  name: string;
  full_name: string;
  html_url: string;
  default_branch: string;
  primary_language?: string;
  license_spdx?: string;
  license_name?: string;
  stars_count: number;
  open_issues_count: number;
  is_fork: boolean;
  is_archived: boolean;
  is_gsoc?: boolean;
  gsoc_org_name?: string;
}

export interface RankingBreakdown {
  skill_match: number;
  clarity_score: number;
  repo_health_score: number;
  effort_score: number;
  reasons: string[];
  has_blocker_risk?: boolean;
  matched_skills?: string[];
}

export interface ActiveTaskSummary {
  id: string;
  workflow_state: string;
  worktree_path?: string;
  branch_name?: string;
  assignment_required: boolean;
  pr_number?: number;
  pr_url?: string;
}

export interface Issue {
  id: string;
  repository_id: string;
  github_id: number;
  issue_number: number;
  title: string;
  body?: string;
  author?: string;
  html_url: string;
  state: string;
  labels: Array<{ name: string; color?: string } | string>;
  assignees: any[];
  comments_count: number;
  github_created_at?: string;
  is_eligible: boolean;
  ineligibility_reason?: string;
  license_status: string;
  policy_status: string;
  ranking_score: number;
  difficulty_estimate: 'beginner' | 'intermediate' | 'advanced';
  estimated_effort_hours: number;
  ranking_breakdown?: RankingBreakdown;
  ai_summary?: string;
  last_verified_at?: string;
  repository?: Repository;
  active_task?: ActiveTaskSummary;

  // Phase 4 Bounty Fields
  bounty_amount?: number;
  bounty_currency?: string;
  bounty_platform?: string;
  bounty_url?: string;
  bounty_status?: string;
}

export interface BountyStats {
  total_available_usd: number;
  total_bounties_count: number;
  average_bounty_usd: number;
  claimed_bounties_count: number;
  potential_earnings_usd: number;
  top_platform: string;
}

export interface SSOConfig {
  sso_provider?: string;
  sso_metadata_url?: string;
  sso_entity_id?: string;
  sso_enforced: boolean;
  sso_configured: boolean;
}

export interface SSOTestResult {
  status: string;
  message: string;
  provider: string;
  entity_id?: string;
  endpoints_detected?: Record<string, string>;
}

export interface ImplementationBrief {
  brief_path?: string;
  prompt_text?: string;
  default_branch?: string;
  issue_number?: number;
  repository?: string;
  title?: string;
  category?: 'bug' | 'feature' | 'refactor' | 'documentation' | string;
  primary_language?: string;
  executive_summary?: string;
  root_cause_analysis?: string;
  extracted_errors?: string[];
  affected_files?: string[];
  proposed_plan?: string[];
  test_strategy?: {
    runner: string;
    command: string;
    verification: string;
  };
  rule_check?: {
    assignment_required: boolean;
    workflow_state: string;
    rule_title: string;
    rule_explanation: string;
    evidence: string[];
    action_on_approval: string;
    draft_comment?: string;
  };
}

export interface Task {
  id: string;
  issue_id: string;
  workflow_state: string;
  worktree_path?: string;
  branch_name?: string;
  remote_name: string;
  upstream_url?: string;
  fork_owner?: string;
  fork_url?: string;
  implementation_brief?: ImplementationBrief;
  assignment_required: boolean;
  draft_assignment_comment?: string;
  user_approved_assignment: boolean;
  assignment_posted_at?: string;
  assignment_comment_id?: string;
  maintainer_approved: boolean;
  maintainer_notes?: string;
  validation_results?: {
    passed: boolean;
    commands: Array<{
      command: string;
      exit_code: number;
      passed: boolean;
      stdout: string;
      stderr: string;
    }>;
    status: string;
  };
  diff_security_report?: {
    passed: boolean;
    changed_files_count: number;
    changed_files: Array<{ status: string; file: string }>;
    secrets_detected: string[];
    unrelated_files: string[];
    diff_preview: string;
  };
  pr_number?: number;
  pr_url?: string;
  pr_state?: string;
  pr_ci_status?: string;
  pr_review_status?: string;
  pr_review_comments?: Array<{
    id?: string;
    author: string;
    body: string;
    state?: string;
    submitted_at?: string;
  }>;
  pr_merged?: boolean;
  blocked_reason?: string;
  created_at: string;
  updated_at: string;
  issue?: Issue;
}

export interface PlatformSettings {
  github_token_configured: boolean;
  github_username?: string;
  auto_publish_pr: boolean;
  workspace_root: string;
  antigravity_app_path?: string;
  skills_profile: string[];
  discovery_filters: Record<string, any>;
  detected_antigravity_installed: boolean;
  detected_agy_cli: boolean;
}

export interface DiscoveryStatus {
  last_synced_at?: string;
  total_issues: number;
  total_eligible: number;
  rate_limit_remaining: number;
  rate_limit_limit: number;
  rate_limit_reset?: string;
  is_syncing: boolean;
  coverage_label: string;
  errors: string[];
}

export interface AuditLog {
  id: string;
  task_id?: string;
  issue_id?: string;
  action: string;
  actor: string;
  details: Record<string, any>;
  created_at: string;
}

export interface Runner {
  id: string;
  name: string;
  os_info?: string;
  status: 'online' | 'offline' | 'idle' | 'busy' | string;
  system_stats?: Record<string, any>;
  last_heartbeat_at?: string;
  is_active: boolean;
  created_at?: string;
}

export interface RunnerJob {
  id: string;
  task_id: string;
  tenant_id: string;
  runner_id?: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | string;
  payload: Record<string, any>;
  result?: Record<string, any>;
  error_message?: string;
  logs?: string;
  started_at?: string;
  completed_at?: string;
  created_at?: string;
}

export interface PlanFeature {
  name: string;
  included: boolean;
  highlight?: boolean;
}

export interface BillingPlan {
  id: 'starter' | 'pro' | 'team';
  name: string;
  description: string;
  price_monthly: number;
  price_annual: number;
  price_id_monthly: string;
  price_id_annual: string;
  quota_tasks: number | null;
  features: PlanFeature[];
}

export interface SubscriptionInfo {
  tier: 'starter' | 'pro' | 'team';
  status: 'active' | 'trialing' | 'past_due' | 'canceled';
  cancel_at_period_end: boolean;
  current_period_end?: string | null;
  tasks_created_this_month: number;
  monthly_task_limit: number | null;
  is_simulation: boolean;
}

export interface CheckoutSessionResponse {
  checkout_url: string;
  session_id: string;
  is_simulated: boolean;
  plan_tier: string;
  billing_cycle?: string;
}

export interface PortalSessionResponse {
  portal_url: string;
  is_simulated: boolean;
}
