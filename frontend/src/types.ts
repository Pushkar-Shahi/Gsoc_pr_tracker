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
  is_private?: boolean;
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

  // Issue Availability & Linked Pull Requests
  has_open_pr?: boolean;
  linked_pr_count?: number;
  linked_prs?: Array<{
    number: number;
    title: string;
    html_url: string;
    state: string;
    author?: string;
    author_avatar?: string;
    created_at?: string;
  }>;
  is_reserved?: boolean;
  reservation_reason?: string;
  availability_status?: 'AVAILABLE' | 'PR_OPEN' | 'ASSIGNED' | 'RESERVED' | string;

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
  ai_mode?: 'live_byok' | 'deterministic_heuristic' | string;
  ai_provider?: string;
  ai_key_source?: 'organization' | 'personal' | 'env' | 'none' | string;
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
  openai_api_key?: string;
  anthropic_api_key?: string;
  gemini_api_key?: string;
  custom_api_key?: string;
  has_openai_key?: boolean;
  has_anthropic_key?: boolean;
  has_gemini_key?: boolean;
  has_custom_key?: boolean;
  enforce_shared_keys?: boolean;
  preferred_ai_provider?: string;
  custom_endpoint?: string;
  triage_policy?: Record<string, any>;
  skill_weights?: Record<string, number>;
  tag_weights?: Record<string, number>;
  org_openai_api_key?: string;
  org_anthropic_api_key?: string;
  org_gemini_api_key?: string;
  org_custom_api_key?: string;
  has_org_openai_key?: boolean;
  has_org_anthropic_key?: boolean;
  has_org_gemini_key?: boolean;
  has_org_custom_key?: boolean;
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
  task_id?: string;
  tenant_id?: string;
  runner_id?: string;
  job_type?: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | string;
  priority?: number;
  payload: Record<string, any>;
  result?: Record<string, any>;
  error_message?: string;
  logs?: string;
  started_at?: string;
  completed_at?: string;
  created_at?: string;
}

export interface WebhookSubscription {
  id: string;
  repo_full_name: string;
  webhook_secret: string;
  events: string[];
  is_active: boolean;
  deliveries_count: number;
  last_delivery_at?: string | null;
  created_at?: string | null;
}

export interface PrivateRepositorySummary {
  id: string;
  full_name: string;
  html_url: string;
  primary_language?: string | null;
  stars_count: number;
  open_issues_count: number;
  last_inspected_at?: string | null;
}

export interface ContributorVelocity {
  user_id: string;
  username: string;
  avatar_url?: string | null;
  role: string;
  tasks_count: number;
  prs_opened: number;
  prs_merged: number;
  ci_passing: number;
}

export interface TeamVelocityReport {
  organization_id: string;
  total_tasks: number;
  total_prs: number;
  open_prs: number;
  merged_prs: number;
  changes_requested_prs: number;
  merge_rate_pct: number;
  ci_pass_rate_pct: number;
  avg_cycle_hours: number;
  seat_count: number;
  contributors: ContributorVelocity[];
  recent_merges: Array<{
    task_id: string;
    pr_number?: number;
    pr_url?: string;
    repo: string;
    title: string;
    updated_at?: string | null;
  }>;
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
  currency?: string;
  currency_symbol?: string;
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
  free_beta_mode?: boolean;
  plan_display_name?: string;
  is_admin?: boolean;
  pending_upi_count?: number;
  pending_admin_upi_count?: number;
  trial_active?: boolean;
  trial_expired?: boolean;
  trial_days_remaining?: number;
  trial_total_days?: number;
  trial_ends_at?: string | null;
}

export interface UpiConfig {
  upi_vpa: string;
  payee_name: string;
  qr_image_url: string;
  currency: string;
  currency_symbol: string;
  suggested_support_amounts: number[];
  autopay_available: boolean;
  autopay_note: string;
  plan_pricing?: Record<string, { monthly: number; annual: number; name: string }>;
}

export interface UpiPaymentRequest {
  id: string;
  tenant_id: string;
  user_id?: string | null;
  payer_username?: string | null;
  payer_email?: string | null;
  payment_purpose: 'plan' | 'support';
  plan_tier?: 'pro' | 'team' | null;
  billing_cycle?: 'monthly' | 'annual' | 'one_time' | null;
  amount_inr: number;
  upi_vpa: string;
  utr_number: string;
  payer_upi_id?: string | null;
  note?: string | null;
  status: 'pending' | 'approved' | 'rejected';
  admin_note?: string | null;
  reviewed_by_user_id?: string | null;
  reviewed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
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

export interface Organization {
  id: string;
  name: string;
  slug: string;
  is_personal: boolean;
  billing_tier: string;
  role: 'owner' | 'admin' | 'member';
  is_active: boolean;
  member_count: number;
}

export interface OrganizationMember {
  id: string;
  user_id: string;
  username: string;
  name?: string;
  email?: string;
  avatar_url?: string;
  role: 'owner' | 'admin' | 'member';
}

export interface AdminRuntimeConfig {
  free_beta_mode: boolean;
  free_trial_days: number;
  free_tier_credit_limit: number;
  upi_vpa: string;
  github_token_configured?: boolean;
}

export interface AdminOverview {
  users: { total: number; active: number; suspended: number; superusers: number };
  organizations: { total: number; by_tier: Record<string, number>; active_trials: number };
  issues: {
    total: number;
    eligible_open: number;
    repositories: number;
    last_scan_at?: string | null;
    worker_running: boolean;
  };
  tasks: { total: number; pr_created: number; merged: number; blocked: number };
  runners: { total: number; online: number; active_jobs: number };
  upi: {
    pending_count: number;
    approved_count: number;
    rejected_count: number;
    plan_revenue_inr: number;
    support_tips_inr: number;
    total_revenue_inr: number;
  };
  runtime: AdminRuntimeConfig;
}

export interface AdminWorkspaceSummary {
  org_id: string;
  org_name: string;
  is_personal: boolean;
  role: string;
  billing_tier: string;
  subscription_status: string;
  trial_active: boolean;
  trial_expired: boolean;
  trial_days_remaining: number;
  tasks_used: number;
  task_limit: number | null;
}

export interface AdminUserRecord {
  id: string;
  github_username: string;
  email?: string | null;
  name?: string | null;
  avatar_url?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  is_current_admin: boolean;
  tasks_total: number;
  workspaces: AdminWorkspaceSummary[];
  created_at?: string | null;
}

export interface AdminTaskRecord {
  id: string;
  workflow_state: string;
  issue_number: number;
  issue_title: string;
  issue_url: string;
  repo_full_name: string;
  username?: string | null;
  org_id?: string | null;
  org_name?: string | null;
  pr_number?: number | null;
  pr_url?: string | null;
  pr_merged: boolean;
  blocked_reason?: string | null;
  updated_at?: string | null;
}

export interface AdminAuditRecord {
  id: string;
  action: string;
  actor: string;
  username?: string | null;
  org_name?: string | null;
  tenant_id?: string | null;
  task_id?: string | null;
  details: Record<string, any>;
  created_at?: string | null;
}
