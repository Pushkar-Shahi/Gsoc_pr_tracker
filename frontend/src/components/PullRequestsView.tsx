import React, { useState, useMemo, useEffect } from 'react';
import { 
  GitPullRequest, ExternalLink, CheckCircle2, Clock, 
  AlertCircle, ShieldCheck, GitBranch, RefreshCw, MessageSquare,
  AlertTriangle, Terminal, Check, Trash2, Columns, List, 
  ArrowUpDown, Download, Sparkles, Filter, X, User, BarChart3, Users
} from 'lucide-react';
import { Task, TeamVelocityReport } from '../types';
import { syncPRStatus, fetchOrganizations, fetchTeamVelocity } from '../api';

interface PullRequestsViewProps {
  tasks: Task[];
  onOpenWorkspace?: (task: Task) => void;
  onRefreshTasks: () => void;
  onUntrackItem?: (taskId: string) => Promise<void>;
  onImportAuthorPRs?: (username?: string) => Promise<void>;
}

type SortField = 'updated' | 'repo' | 'number' | 'status';
type ViewMode = 'columns' | 'list';

export const PullRequestsView: React.FC<PullRequestsViewProps> = ({
  tasks,
  onOpenWorkspace,
  onRefreshTasks,
  onUntrackItem,
  onImportAuthorPRs,
}) => {
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('columns');
  const [sortBy, setSortBy] = useState<SortField>('updated');
  const [sortAsc, setSortAsc] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importUsername, setImportUsername] = useState(() => {
    try {
      return localStorage.getItem('issuetopr_gh_user') || 'Pushkar-Shahi';
    } catch {
      return 'Pushkar-Shahi';
    }
  });
  const [teamVelocity, setTeamVelocity] = useState<TeamVelocityReport | null>(null);
  const [velocityLocked, setVelocityLocked] = useState(false);
  const [showVelocity, setShowVelocity] = useState(true);

  useEffect(() => {
    fetchOrganizations()
      .then((orgs) => {
        const active = orgs.find((o) => o.is_active) || orgs[0];
        if (!active) return;
        return fetchTeamVelocity(active.id)
          .then((report) => {
            setTeamVelocity(report);
            setVelocityLocked(false);
          })
          .catch((err: any) => {
            if (err.code === 'TIER_UPGRADE_REQUIRED') {
              setVelocityLocked(true);
            }
          });
      })
      .catch(() => null);
  }, [tasks.length]);

  // Filter tasks that have PR number or PR URL
  const prTasks = useMemo(() => {
    return tasks.filter(t => Boolean(t.pr_url || t.pr_number));
  }, [tasks]);

  const handleSyncPR = async (taskId: string) => {
    try {
      setSyncingId(taskId);
      setSyncMessage(null);
      await syncPRStatus(taskId);
      onRefreshTasks();
      setSyncMessage('Pull request status synced with GitHub.');
      setTimeout(() => setSyncMessage(null), 4000);
    } catch (err: any) {
      setSyncMessage(`Sync error: ${err.message}`);
    } finally {
      setSyncingId(null);
    }
  };

  const handleImportSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!onImportAuthorPRs) return;
    const target = importUsername.trim() || 'Pushkar-Shahi';
    setIsImporting(true);
    setSyncMessage(null);
    try {
      await onImportAuthorPRs(target);
      onRefreshTasks();
      setShowImportModal(false);
      setSyncMessage(`✓ Successfully searched GitHub and imported PRs for @${target}!`);
      setTimeout(() => setSyncMessage(null), 5000);
    } catch (err: any) {
      setSyncMessage(`Import error: ${err.message}`);
    } finally {
      setIsImporting(false);
    }
  };

  // Sorting function
  const sortTasks = (items: Task[]) => {
    return [...items].sort((a, b) => {
      let comparison = 0;
      if (sortBy === 'updated') {
        const timeA = new Date(a.updated_at || 0).getTime();
        const timeB = new Date(b.updated_at || 0).getTime();
        comparison = timeB - timeA;
      } else if (sortBy === 'repo') {
        const repoA = a.issue?.repository?.full_name || '';
        const repoB = b.issue?.repository?.full_name || '';
        comparison = repoA.localeCompare(repoB);
      } else if (sortBy === 'number') {
        const numA = a.pr_number || a.issue?.issue_number || 0;
        const numB = b.pr_number || b.issue?.issue_number || 0;
        comparison = numB - numA;
      } else if (sortBy === 'status') {
        const getPriority = (t: Task) => {
          if (t.pr_review_status === 'CHANGES_REQUESTED' || t.pr_ci_status === 'failure') return 1;
          if (t.pr_ci_status === 'pending') return 2;
          if (t.pr_state === 'open' && !t.pr_merged) return 3;
          if (t.pr_merged) return 4;
          return 5;
        };
        comparison = getPriority(a) - getPriority(b);
      }
      return sortAsc ? -comparison : comparison;
    });
  };

  // Group into columns
  const activePRs = useMemo(() => {
    return sortTasks(prTasks.filter(t => 
      !t.pr_merged && 
      t.pr_state !== 'closed' && 
      t.pr_review_status !== 'CHANGES_REQUESTED' && 
      t.pr_ci_status !== 'failure'
    ));
  }, [prTasks, sortBy, sortAsc]);

  const attentionPRs = useMemo(() => {
    return sortTasks(prTasks.filter(t => 
      !t.pr_merged && 
      (t.pr_review_status === 'CHANGES_REQUESTED' || t.pr_ci_status === 'failure')
    ));
  }, [prTasks, sortBy, sortAsc]);

  const mergedPRs = useMemo(() => {
    return sortTasks(prTasks.filter(t => t.pr_merged || t.pr_state === 'closed'));
  }, [prTasks, sortBy, sortAsc]);

  const allSortedPRs = useMemo(() => {
    return sortTasks(prTasks);
  }, [prTasks, sortBy, sortAsc]);

  const getCIStatusBadge = (status?: string) => {
    switch (status) {
      case 'success':
        return (
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 dark:text-white dark:bg-white/10 dark:border-white/20 px-2 py-0.5 rounded">
            <CheckCircle2 className="w-3 h-3 text-emerald-600 dark:text-white" />
            <span>Checks Passing</span>
          </span>
        );
      case 'failure':
        return (
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-rose-700 bg-rose-50 border border-rose-200 dark:text-white dark:bg-white/20 dark:border-white/40 px-2 py-0.5 rounded">
            <AlertCircle className="w-3 h-3 text-rose-600 dark:text-white" />
            <span>Checks Failing</span>
          </span>
        );
      case 'pending':
        return (
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 dark:text-neutral-300 dark:bg-neutral-900 dark:border-white/10 px-2 py-0.5 rounded">
            <Clock className="w-3 h-3 text-amber-600 dark:text-white animate-spin" />
            <span>CI Pending</span>
          </span>
        );
      default:
        return (
          <span className="text-[11px] text-slate-500 dark:text-neutral-400 font-mono">
            {status || 'Preflight Passed'}
          </span>
        );
    }
  };

  const getReviewBadge = (status?: string, isMerged?: boolean) => {
    if (isMerged) {
      return (
        <span className="text-[10px] sm:text-[11px] font-bold px-2 sm:px-2.5 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 dark:bg-white dark:text-black dark:border-white flex items-center gap-1">
          <Sparkles className="w-3 h-3 text-purple-500 dark:text-black" />
          <span>MERGED UPSTREAM</span>
        </span>
      );
    }
    switch (status) {
      case 'CHANGES_REQUESTED':
        return (
          <span className="text-[10px] sm:text-[11px] font-bold px-2 sm:px-2.5 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 dark:bg-neutral-900 dark:text-white dark:border-white/30 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3 text-rose-600 dark:text-white" />
            <span>Changes Requested</span>
          </span>
        );
      case 'APPROVED':
        return (
          <span className="text-[10px] sm:text-[11px] font-bold px-2 sm:px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-white/15 dark:text-white dark:border-white/30 flex items-center gap-1">
            <Check className="w-3 h-3 text-emerald-600 dark:text-white" />
            <span>Approved by Maintainer</span>
          </span>
        );
      case 'COMMENTED':
        return (
          <span className="text-[10px] sm:text-[11px] font-semibold px-2 sm:px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 dark:bg-neutral-900 dark:text-neutral-200 dark:border-white/15">
            Maintainer Commented
          </span>
        );
      default:
        return (
          <span className="text-[10px] sm:text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 dark:bg-white/5 dark:text-neutral-400 dark:border-white/10">
            Awaiting Review
          </span>
        );
    }
  };

  const renderPRCard = (task: Task, isCompact = false) => {
    const isChangesRequested = task.pr_review_status === 'CHANGES_REQUESTED';
    const isMerged = task.pr_merged;

    return (
      <div
        key={task.id}
        className={`mobile-card-render bg-[#0c101a] border rounded-2xl shadow-xl transition-all duration-200 space-y-3.5 hover:shadow-2xl hover:bg-[#0f1422] ${
          isMerged 
            ? 'border-purple-500/30' 
            : isChangesRequested 
            ? 'border-rose-500/30' 
            : 'border-white/10 hover:border-white/25'
        } ${isCompact ? 'p-3.5 sm:p-4' : 'p-4 sm:p-5'}`}
      >
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
          <div className="space-y-1.5 flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-[11px] sm:text-xs px-2.5 py-0.5 rounded-lg bg-white/5 border border-white/10 text-white font-semibold truncate max-w-[180px] sm:max-w-[240px]" title={task.issue?.repository?.full_name}>
                {task.issue?.repository?.full_name}
              </span>
              <span className="text-xs font-bold text-neutral-300 font-mono">
                PR #{task.pr_number}
              </span>
              {getReviewBadge(task.pr_review_status, task.pr_merged)}
            </div>

            <h3 className="text-sm sm:text-base font-semibold text-white line-clamp-2 leading-snug">
              {task.issue?.title}
            </h3>

            {/* Direct Links Bar */}
            <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
              {task.issue?.html_url && (
                <a
                  href={task.issue.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="min-h-[32px] px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 hover:border-white/20 text-neutral-300 hover:text-white flex items-center gap-1.5 transition text-[11px]"
                  title="Open original issue on GitHub"
                >
                  <span>Issue #{task.issue.issue_number}</span>
                  <ExternalLink className="w-2.5 h-2.5" />
                </a>
              )}

              {task.assignment_comment_id && (
                <a
                  href={task.assignment_comment_id.startsWith('http') ? task.assignment_comment_id : `${task.issue?.html_url}#issuecomment-${task.assignment_comment_id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="min-h-[32px] px-2.5 py-1 rounded-lg bg-cyan-50 hover:bg-cyan-100 border border-cyan-200 text-cyan-700 dark:bg-cyan-950/40 dark:border-cyan-500/30 dark:hover:bg-cyan-900/50 dark:text-cyan-300 flex items-center gap-1.5 transition text-[11px]"
                  title="View assignment comment on GitHub"
                >
                  <MessageSquare className="w-2.5 h-2.5 text-cyan-400" />
                  <span>Comment</span>
                  <ExternalLink className="w-2.5 h-2.5 text-cyan-400" />
                </a>
              )}
            </div>
          </div>

          <div className="flex items-center gap-1.5 self-start shrink-0">
            <button
              onClick={() => handleSyncPR(task.id)}
              disabled={syncingId === task.id}
              className="p-2 sm:p-1.5 min-w-[36px] min-h-[36px] sm:min-w-0 sm:min-h-0 rounded-xl bg-white/5 hover:bg-white/10 text-neutral-300 hover:text-white text-xs border border-white/10 transition flex items-center justify-center active:scale-95"
              title="Sync PR status, CI runs, and maintainer reviews"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${syncingId === task.id ? 'animate-spin' : ''}`} />
            </button>

            <a
              href={task.pr_url}
              target="_blank"
              rel="noreferrer"
              className="min-h-[36px] px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white dark:bg-white dark:hover:bg-neutral-200 dark:text-black text-xs font-semibold shadow-sm shadow-blue-600/20 transition flex items-center gap-1.5 active:scale-95"
            >
              <span>GitHub</span>
              <ExternalLink className="w-3 h-3" />
            </a>

            {onUntrackItem && (
              <button
                onClick={() => onUntrackItem(task.id)}
                className="p-2 sm:p-1.5 min-w-[36px] min-h-[36px] sm:min-w-0 sm:min-h-0 rounded-xl text-neutral-400 hover:text-rose-400 hover:bg-rose-950/20 border border-transparent hover:border-rose-500/20 transition flex items-center justify-center"
                title="Remove PR from tracking"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Changes Requested Banner */}
        {isChangesRequested && (
          <div className="bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-500/30 rounded-xl p-3 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-rose-700 dark:text-rose-300 font-semibold">
                <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                <span>Maintainer requested changes</span>
              </div>
              {onOpenWorkspace && (
                <button
                  onClick={() => onOpenWorkspace(task)}
                  className="px-2.5 py-1 rounded bg-white hover:bg-neutral-200 text-black text-[11px] font-semibold transition flex items-center gap-1"
                >
                  <Terminal className="w-3 h-3" />
                  <span>Resume</span>
                </button>
              )}
            </div>
            {task.pr_review_comments && task.pr_review_comments.length > 0 && (
              <div className="text-[11px] text-neutral-300 bg-[#05080f] rounded-lg p-2.5 border border-white/10">
                <span className="text-white font-semibold">@{task.pr_review_comments[0].author}:</span> {task.pr_review_comments[0].body}
              </div>
            )}
          </div>
        )}

        {/* PR Status & Branch footer */}
        <div className="bg-[#05080f] border border-white/10 rounded-xl p-2.5 flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-400">
          <div className="flex items-center gap-1.5 font-mono text-[11px]">
            <GitBranch className="w-3 h-3 text-neutral-300" />
            <span className="text-neutral-200 truncate max-w-[140px]">{task.branch_name || 'main'}</span>
          </div>

          <div className="flex items-center gap-1.5">
            {getCIStatusBadge(task.pr_ci_status)}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6 animate-fade-in-up">
      {/* Top Action Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-extrabold text-slate-900 dark:text-white">Pull Requests Dashboard</h2>
            <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-800 border border-slate-200 dark:bg-white/10 dark:text-white dark:border-white/20">
              {prTasks.length} Tracked
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-neutral-400 mt-1">
            Real-time dashboard tracking active pull requests, CI test runs, and maintainer reviews.
          </p>
        </div>

        {/* Global Controls: Import, Sort, View Mode */}
        <div className="flex items-center gap-2.5 shrink-0 flex-wrap sm:flex-nowrap">
          {/* Import PRs button */}
          {onImportAuthorPRs && (
            <button
              onClick={() => setShowImportModal(true)}
              disabled={isImporting}
              className="h-9 px-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition flex items-center gap-2 shadow-sm shadow-blue-600/20 active:scale-95 disabled:opacity-50 shrink-0 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
              title="Search GitHub for all pull requests authored by you and import them"
            >
              <Sparkles className={`w-3.5 h-3.5 ${isImporting ? 'animate-spin' : ''}`} />
              <span>{isImporting ? 'Importing PRs...' : 'Import My PRs'}</span>
            </button>
          )}

          {/* Sort Selector - shown when PRs exist */}
          {prTasks.length > 0 && (
            <div className="flex items-center gap-1 bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-xl px-2 h-9 text-xs shadow-sm">
              <span className="text-slate-500 dark:text-neutral-400 text-[11px] flex items-center gap-1">
                <ArrowUpDown className="w-3 h-3 text-slate-400 dark:text-neutral-400" />
                <span>Sort:</span>
              </span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortField)}
                className="bg-transparent text-slate-800 dark:text-neutral-200 text-xs focus:outline-none cursor-pointer pr-1 font-medium"
              >
                <option value="updated" className="bg-white dark:bg-[#0c101a] text-slate-900 dark:text-white">Recently Updated</option>
                <option value="repo" className="bg-white dark:bg-[#0c101a] text-slate-900 dark:text-white">Repository Name</option>
                <option value="number" className="bg-white dark:bg-[#0c101a] text-slate-900 dark:text-white">PR Number</option>
                <option value="status" className="bg-white dark:bg-[#0c101a] text-slate-900 dark:text-white">Health Priority</option>
              </select>
              <button
                onClick={() => setSortAsc(!sortAsc)}
                className="p-1 min-w-[24px] min-h-[24px] text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white rounded transition flex items-center justify-center"
                title={sortAsc ? 'Ascending' : 'Descending'}
              >
                {sortAsc ? '↑' : '↓'}
              </button>
            </div>
          )}

          {/* View Mode Toggle: Columns vs List - shown when PRs exist */}
          {prTasks.length > 0 && (
            <div className="flex items-center bg-slate-100 dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-xl p-0.5 h-9 text-xs shadow-sm">
              <button
                onClick={() => setViewMode('columns')}
                className={`p-1.5 rounded-lg transition flex items-center justify-center ${
                  viewMode === 'columns'
                    ? 'bg-white text-blue-600 shadow-sm border border-slate-200/80 dark:bg-white dark:text-black font-semibold'
                    : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white'
                }`}
                title="Columns / Board View"
              >
                <Columns className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded-lg transition flex items-center justify-center ${
                  viewMode === 'list'
                    ? 'bg-white text-blue-600 shadow-sm border border-slate-200/80 dark:bg-white dark:text-black font-semibold'
                    : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white'
                }`}
                title="List View"
              >
                <List className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      {syncMessage && (
        <div className="p-3 bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/20 rounded-xl text-xs text-slate-900 dark:text-white flex items-center gap-2 animate-fade-in-up shadow-sm dark:shadow-lg">
          <RefreshCw className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400 shrink-0" />
          <span>{syncMessage}</span>
        </div>
      )}

      {/* Centralized Team PR Velocity Dashboard */}
      {(teamVelocity || velocityLocked) && (
        <div className="rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 p-5 shadow-sm dark:shadow-xl space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-500/30">
                <BarChart3 className="w-4 h-4" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    Centralized Team PR Velocity Dashboard
                  </h3>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 dark:bg-indigo-500/15 dark:text-indigo-300 dark:border-indigo-500/30">
                    TEAM METRICS
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 dark:text-neutral-400">
                  Organization-wide merge velocity, CI pass rate, cycle time, and contributor breakdown.
                </p>
              </div>
            </div>
            {teamVelocity && (
              <button
                type="button"
                onClick={() => setShowVelocity((v) => !v)}
                className="text-xs font-semibold text-slate-600 dark:text-neutral-300 hover:text-slate-900 dark:hover:text-white px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-white/5"
              >
                {showVelocity ? 'Hide Analytics' : 'Show Analytics'}
              </button>
            )}
          </div>

          {velocityLocked ? (
            <div className="p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-500/30 text-xs text-amber-800 dark:text-amber-300">
              Upgrade to <strong>Engineering Team (₹300/mo)</strong> to unlock organization-wide contributor velocity analytics and cycle-time tracking.
            </div>
          ) : (
            teamVelocity &&
            showVelocity && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10">
                    <div className="text-[10px] font-mono uppercase text-slate-500 dark:text-neutral-400">Merge Rate</div>
                    <div className="text-xl font-extrabold text-emerald-600 dark:text-emerald-400 mt-0.5 font-mono">
                      {teamVelocity.merge_rate_pct}%
                    </div>
                    <div className="text-[11px] text-slate-500 dark:text-neutral-400">
                      {teamVelocity.merged_prs} / {teamVelocity.total_prs} merged
                    </div>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10">
                    <div className="text-[10px] font-mono uppercase text-slate-500 dark:text-neutral-400">CI Health</div>
                    <div className="text-xl font-extrabold text-blue-600 dark:text-blue-400 mt-0.5 font-mono">
                      {teamVelocity.ci_pass_rate_pct}%
                    </div>
                    <div className="text-[11px] text-slate-500 dark:text-neutral-400">
                      {teamVelocity.open_prs} active open PRs
                    </div>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10">
                    <div className="text-[10px] font-mono uppercase text-slate-500 dark:text-neutral-400">Avg PR Cycle</div>
                    <div className="text-xl font-extrabold text-slate-900 dark:text-white mt-0.5 font-mono">
                      {teamVelocity.avg_cycle_hours}h
                    </div>
                    <div className="text-[11px] text-slate-500 dark:text-neutral-400">
                      {teamVelocity.total_tasks} total org tasks
                    </div>
                  </div>
                  <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10">
                    <div className="text-[10px] font-mono uppercase text-slate-500 dark:text-neutral-400">Team Seats</div>
                    <div className="text-xl font-extrabold text-purple-600 dark:text-purple-400 mt-0.5 font-mono flex items-center gap-1.5">
                      <Users className="w-4 h-4" />
                      <span>{teamVelocity.seat_count}</span>
                    </div>
                    <div className="text-[11px] text-slate-500 dark:text-neutral-400">
                      {teamVelocity.changes_requested_prs} changes requested
                    </div>
                  </div>
                </div>

                {teamVelocity.contributors.length > 0 && (
                  <div className="rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 divide-y divide-slate-200 dark:divide-white/10">
                    {teamVelocity.contributors.slice(0, 6).map((c) => (
                      <div key={c.user_id} className="px-4 py-2.5 flex flex-wrap items-center justify-between gap-2 text-xs">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-900 dark:text-white">@{c.username}</span>
                          <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 text-slate-500 dark:text-neutral-400">
                            {c.role}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-[11px] font-mono text-slate-600 dark:text-neutral-300">
                          <span>Tasks: <strong>{c.tasks_count}</strong></span>
                          <span>PRs: <strong>{c.prs_opened}</strong></span>
                          <span className="text-emerald-600 dark:text-emerald-400">Merged: <strong>{c.prs_merged}</strong></span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          )}
        </div>
      )}

      {/* Empty State */}
      {prTasks.length === 0 ? (
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-10 sm:p-14 text-center space-y-4 shadow-sm dark:shadow-xl">
          <div className="w-14 h-14 rounded-2xl bg-blue-50 dark:bg-white/5 border border-blue-100 dark:border-white/10 flex items-center justify-center mx-auto text-blue-600 dark:text-neutral-400">
            <GitPullRequest className="w-7 h-7" />
          </div>
          <h3 className="text-base font-bold text-slate-900 dark:text-white">No pull requests tracked yet</h3>
          <p className="text-xs text-slate-500 dark:text-neutral-400 max-w-md mx-auto leading-relaxed">
            You can paste any GitHub PR link into the Tracked Items view, or click below to automatically import all PRs authored by you.
          </p>
          {onImportAuthorPRs && (
            <button
              onClick={() => setShowImportModal(true)}
              disabled={isImporting}
              className="min-h-[42px] px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow-md shadow-blue-600/25 active:scale-95 transition inline-flex items-center gap-2 dark:bg-white dark:hover:bg-neutral-200 dark:text-black"
            >
              <Sparkles className="w-4 h-4" />
              <span>{isImporting ? 'Searching GitHub...' : 'Import My Pull Requests'}</span>
            </button>
          )}
        </div>
      ) : viewMode === 'columns' ? (
        /* Multi-Column Board View with Dedicated Merged Column */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          {/* Column 1: Active & In Review */}
          <div className="space-y-4 bg-slate-50 dark:bg-[#080c14]/80 border border-slate-200 dark:border-white/10 rounded-2xl p-4 min-h-[400px] shadow-sm dark:shadow-lg">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
                <h3 className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">Active PRs</h3>
              </div>
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-white/10 text-white border border-white/10">
                {activePRs.length}
              </span>
            </div>

            {activePRs.length === 0 ? (
              <div className="p-8 text-center text-xs text-neutral-500 italic border border-dashed border-white/10 rounded-2xl">
                No active in-review pull requests
              </div>
            ) : (
              <div className="space-y-4">
                {activePRs.map(task => renderPRCard(task, true))}
              </div>
            )}
          </div>

          {/* Column 2: Needs Attention */}
          <div className="space-y-4 bg-slate-50 dark:bg-[#080c14]/80 border border-slate-200 dark:border-white/10 rounded-2xl p-4 min-h-[400px] shadow-sm dark:shadow-lg">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
                <h3 className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">Needs Attention</h3>
              </div>
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-white/10 text-white border border-white/10">
                {attentionPRs.length}
              </span>
            </div>

            {attentionPRs.length === 0 ? (
              <div className="p-8 text-center text-xs text-neutral-500 italic border border-dashed border-white/10 rounded-2xl">
                ✓ All PRs are healthy! No changes requested or CI failures.
              </div>
            ) : (
              <div className="space-y-4">
                {attentionPRs.map(task => renderPRCard(task, true))}
              </div>
            )}
          </div>

          {/* Column 3: Dedicated Merged Column */}
          <div className="space-y-4 bg-[#080c14]/80 border border-purple-500/20 rounded-2xl p-4 min-h-[400px] shadow-lg">
            <div className="flex items-center justify-between border-b border-purple-500/20 pb-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-purple-400 animate-pulse" />
                <h3 className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">Merged Upstream</h3>
              </div>
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                {mergedPRs.length}
              </span>
            </div>

            {mergedPRs.length === 0 ? (
              <div className="p-8 text-center text-xs text-neutral-500 italic border border-dashed border-white/15 rounded-2xl">
                No merged pull requests yet
              </div>
            ) : (
              <div className="space-y-4">
                {mergedPRs.map(task => renderPRCard(task, true))}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* List View */
        <div className="grid grid-cols-1 gap-4">
          {allSortedPRs.map(task => renderPRCard(task, false))}
        </div>
      )}

      {/* Author PR Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="fixed inset-0" onClick={() => !isImporting && setShowImportModal(false)} />
          <div className="relative bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/15 rounded-2xl p-6 sm:p-7 max-w-md w-full shadow-2xl z-10 space-y-5 text-slate-900 dark:text-white">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-white/10 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-white/10 text-white border border-white/10">
                  <GitPullRequest className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Import Pull Requests</h3>
                  <p className="text-[11px] text-neutral-400">Search GitHub for all PRs authored by account</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowImportModal(false)}
                disabled={isImporting}
                className="p-1.5 rounded-xl text-neutral-400 hover:text-white hover:bg-white/5 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleImportSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-neutral-300 flex items-center justify-between">
                  <span>GitHub Username</span>
                  <span className="text-[10px] text-neutral-500">Public search query</span>
                </label>
                <div className="relative flex items-center">
                  <User className="absolute left-3.5 w-4 h-4 text-neutral-500" />
                  <input
                    type="text"
                    value={importUsername}
                    onChange={(e) => setImportUsername(e.target.value)}
                    placeholder="e.g. Pushkar-Shahi"
                    disabled={isImporting}
                    className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-[#05080f] border border-white/10 text-white placeholder-neutral-500 text-xs font-mono focus:outline-none focus:border-white/30 transition"
                    autoFocus
                  />
                </div>
              </div>

              <div className="bg-[#05080f] border border-white/10 rounded-xl p-3.5 text-[11px] text-neutral-400 space-y-1.5 font-sans">
                <p className="text-neutral-200 font-semibold">What will be imported:</p>
                <p>• All open & merged pull requests by <strong className="text-white">@{importUsername.trim() || 'Pushkar-Shahi'}</strong></p>
                <p>• Categorized into Active, Action Required, and Merged</p>
                <p>• Live synchronization of CI checks and maintainer reviews</p>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  disabled={isImporting}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-neutral-400 hover:text-white hover:bg-white/5 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isImporting}
                  className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white dark:bg-white dark:hover:bg-neutral-200 dark:text-black font-bold text-xs flex items-center gap-2 shadow-md shadow-blue-600/20 active:scale-95 transition disabled:opacity-50"
                >
                  <Sparkles className={`w-3.5 h-3.5 text-black ${isImporting ? 'animate-spin' : ''}`} />
                  <span>{isImporting ? 'Searching GitHub...' : 'Search & Import PRs'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default PullRequestsView;
