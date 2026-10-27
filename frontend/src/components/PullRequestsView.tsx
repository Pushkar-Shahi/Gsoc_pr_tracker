import React, { useState, useMemo } from 'react';
import { 
  GitPullRequest, ExternalLink, CheckCircle2, Clock, 
  AlertCircle, ShieldCheck, GitBranch, RefreshCw, MessageSquare,
  AlertTriangle, Terminal, Check, Trash2, Columns, List, 
  ArrowUpDown, Download, Sparkles, Filter
} from 'lucide-react';
import { Task } from '../types';
import { syncPRStatus } from '../api';

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

  const handleImportClick = async () => {
    if (!onImportAuthorPRs) return;
    setIsImporting(true);
    setSyncMessage(null);
    try {
      await onImportAuthorPRs();
      onRefreshTasks();
      setSyncMessage('✓ Successfully searched GitHub and imported your pull requests!');
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
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-white bg-white/10 px-2 py-0.5 rounded border border-white/20">
            <CheckCircle2 className="w-3 h-3 text-white" />
            <span>Checks Passing</span>
          </span>
        );
      case 'failure':
        return (
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-white bg-white/20 px-2 py-0.5 rounded border border-white/40">
            <AlertCircle className="w-3 h-3 text-white" />
            <span>Checks Failing</span>
          </span>
        );
      case 'pending':
        return (
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-neutral-300 bg-neutral-900 px-2 py-0.5 rounded border border-white/10">
            <Clock className="w-3 h-3 text-white animate-spin" />
            <span>CI Pending</span>
          </span>
        );
      default:
        return (
          <span className="text-[11px] text-neutral-400 font-mono">
            {status || 'Preflight Passed'}
          </span>
        );
    }
  };

  const getReviewBadge = (status?: string, isMerged?: boolean) => {
    if (isMerged) {
      return (
        <span className="text-[10px] sm:text-[11px] font-bold px-2 sm:px-2.5 py-0.5 rounded-full bg-white text-black border border-white flex items-center gap-1">
          <Sparkles className="w-3 h-3 text-black" />
          <span>MERGED UPSTREAM</span>
        </span>
      );
    }
    switch (status) {
      case 'CHANGES_REQUESTED':
        return (
          <span className="text-[10px] sm:text-[11px] font-bold px-2 sm:px-2.5 py-0.5 rounded-full bg-neutral-900 text-white border border-white/30 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3 text-white" />
            <span>Changes Requested</span>
          </span>
        );
      case 'APPROVED':
        return (
          <span className="text-[10px] sm:text-[11px] font-bold px-2 sm:px-2.5 py-0.5 rounded-full bg-white/15 text-white border border-white/30 flex items-center gap-1">
            <Check className="w-3 h-3 text-white" />
            <span>Approved by Maintainer</span>
          </span>
        );
      case 'COMMENTED':
        return (
          <span className="text-[10px] sm:text-[11px] font-semibold px-2 sm:px-2.5 py-0.5 rounded-full bg-neutral-900 text-neutral-200 border border-white/15">
            Maintainer Commented
          </span>
        );
      default:
        return (
          <span className="text-[10px] sm:text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#111111] text-neutral-400 border border-white/10">
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
        className={`bg-[#080808] border rounded-2xl shadow-xl transition-all duration-200 space-y-3.5 hover:shadow-2xl ${
          isMerged 
            ? 'border-white/30 bg-[#0c0c0c]' 
            : isChangesRequested 
            ? 'border-white/30 bg-[#0a0a0a]' 
            : 'border-white/10 hover:border-white/25'
        } ${isCompact ? 'p-3.5 sm:p-4' : 'p-4 sm:p-5'}`}
      >
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
          <div className="space-y-1.5 flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-[11px] sm:text-xs px-2.5 py-0.5 rounded bg-[#111111] border border-white/10 text-white font-semibold truncate max-w-[180px] sm:max-w-[240px]" title={task.issue?.repository?.full_name}>
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
                  className="min-h-[32px] px-2.5 py-1 rounded-lg bg-[#111111] border border-white/10 hover:border-white/20 text-neutral-300 hover:text-white flex items-center gap-1.5 transition text-[11px]"
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
                  className="min-h-[32px] px-2.5 py-1 rounded-lg bg-[#141414] border border-white/15 hover:border-white/30 text-white flex items-center gap-1.5 transition text-[11px]"
                  title="View assignment comment on GitHub"
                >
                  <MessageSquare className="w-2.5 h-2.5 text-neutral-400" />
                  <span>Comment</span>
                  <ExternalLink className="w-2.5 h-2.5 text-neutral-400" />
                </a>
              )}
            </div>
          </div>

          <div className="flex items-center gap-1.5 self-start shrink-0">
            <button
              onClick={() => handleSyncPR(task.id)}
              disabled={syncingId === task.id}
              className="p-2 sm:p-1.5 min-w-[36px] min-h-[36px] sm:min-w-0 sm:min-h-0 rounded-lg bg-[#111111] hover:bg-[#1a1a1a] text-neutral-300 hover:text-white text-xs border border-white/10 transition flex items-center justify-center"
              title="Sync PR status, CI runs, and maintainer reviews"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-white ${syncingId === task.id ? 'animate-spin' : ''}`} />
            </button>

            <a
              href={task.pr_url}
              target="_blank"
              rel="noreferrer"
              className="min-h-[36px] px-3.5 py-1.5 rounded-lg bg-white hover:bg-neutral-200 text-black text-xs font-semibold shadow-md transition flex items-center gap-1.5"
            >
              <span>GitHub</span>
              <ExternalLink className="w-3 h-3" />
            </a>

            {onUntrackItem && (
              <button
                onClick={() => onUntrackItem(task.id)}
                className="p-2 sm:p-1.5 min-w-[36px] min-h-[36px] sm:min-w-0 sm:min-h-0 rounded-lg text-neutral-500 hover:text-white hover:bg-[#161616] border border-transparent hover:border-white/10 transition flex items-center justify-center"
                title="Remove PR from tracking"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Changes Requested Banner */}
        {isChangesRequested && (
          <div className="bg-[#141414] border border-white/20 rounded-xl p-3 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-white font-semibold">
                <AlertTriangle className="w-3.5 h-3.5 text-white" />
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
              <div className="text-[11px] text-neutral-300 bg-[#000000] rounded p-2 border border-white/10">
                <span className="text-white font-semibold">@{task.pr_review_comments[0].author}:</span> {task.pr_review_comments[0].body}
              </div>
            )}
          </div>
        )}

        {/* PR Status & Branch footer */}
        <div className="bg-[#000000] border border-white/10 rounded-xl p-2.5 flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-400">
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
            <h2 className="text-xl font-extrabold text-white">Pull Requests Dashboard</h2>
            <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-full bg-white/10 text-white border border-white/20">
              {prTasks.length} Tracked
            </span>
          </div>
          <p className="text-xs text-neutral-400 mt-1">
            Real-time AMOLED board tracking active pull requests, CI test runs, and maintainer reviews.
          </p>
        </div>

        {/* Global Controls: Import, Sort, View Mode */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Import PRs button */}
          {onImportAuthorPRs && (
            <button
              onClick={handleImportClick}
              disabled={isImporting}
              className="min-h-[44px] sm:min-h-[38px] px-3.5 py-2 rounded-xl bg-white text-black hover:bg-neutral-200 border border-white text-xs font-semibold transition flex items-center gap-2 shadow-sm active:scale-95 disabled:opacity-50"
              title="Search GitHub for all pull requests authored by you and import them"
            >
              <Sparkles className={`w-3.5 h-3.5 text-black ${isImporting ? 'animate-spin' : ''}`} />
              <span>{isImporting ? 'Importing PRs...' : 'Import My PRs'}</span>
            </button>
          )}

          {/* Sort Selector */}
          <div className="flex items-center gap-1 bg-[#080808] border border-white/10 rounded-xl p-1 text-xs">
            <span className="text-neutral-400 px-1.5 text-[11px] flex items-center gap-1">
              <ArrowUpDown className="w-3 h-3 text-neutral-400" />
              <span>Sort:</span>
            </span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortField)}
              className="bg-transparent text-neutral-200 text-xs focus:outline-none cursor-pointer pr-1 font-medium"
            >
              <option value="updated" className="bg-[#000000] text-white">Recently Updated</option>
              <option value="repo" className="bg-[#000000] text-white">Repository Name</option>
              <option value="number" className="bg-[#000000] text-white">PR Number</option>
              <option value="status" className="bg-[#000000] text-white">Health Priority</option>
            </select>
            <button
              onClick={() => setSortAsc(!sortAsc)}
              className="p-1 min-w-[28px] min-h-[28px] text-neutral-400 hover:text-white rounded transition flex items-center justify-center"
              title={sortAsc ? 'Ascending' : 'Descending'}
            >
              {sortAsc ? '↑' : '↓'}
            </button>
          </div>

          {/* View Mode Toggle: Columns vs List */}
          <div className="flex items-center bg-[#080808] border border-white/10 rounded-xl p-1 text-xs">
            <button
              onClick={() => setViewMode('columns')}
              className={`p-2 sm:p-1.5 min-w-[36px] min-h-[36px] sm:min-w-0 sm:min-h-0 rounded-lg transition flex items-center justify-center ${
                viewMode === 'columns'
                  ? 'bg-white text-black font-semibold'
                  : 'text-neutral-400 hover:text-white'
              }`}
              title="Columns / Board View"
            >
              <Columns className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-2 sm:p-1.5 min-w-[36px] min-h-[36px] sm:min-w-0 sm:min-h-0 rounded-lg transition flex items-center justify-center ${
                viewMode === 'list'
                  ? 'bg-white text-black font-semibold'
                  : 'text-neutral-400 hover:text-white'
              }`}
              title="List View"
            >
              <List className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {syncMessage && (
        <div className="p-3 bg-[#080808] border border-white/20 rounded-xl text-xs text-white flex items-center gap-2 animate-fade-in-up">
          <RefreshCw className="w-3.5 h-3.5 text-white shrink-0" />
          <span>{syncMessage}</span>
        </div>
      )}

      {/* Empty State */}
      {prTasks.length === 0 ? (
        <div className="bg-[#080808] border border-white/10 rounded-3xl p-10 sm:p-14 text-center space-y-4">
          <GitPullRequest className="w-10 h-10 text-neutral-500 mx-auto" />
          <h3 className="text-base font-bold text-white">No pull requests tracked yet</h3>
          <p className="text-xs text-neutral-400 max-w-md mx-auto">
            You can paste any GitHub PR link into the Tracked Items view, or click below to automatically import all PRs authored by you.
          </p>
          {onImportAuthorPRs && (
            <button
              onClick={handleImportClick}
              disabled={isImporting}
              className="min-h-[44px] px-6 py-2.5 rounded-xl bg-white hover:bg-neutral-200 text-black text-xs font-bold transition inline-flex items-center gap-2"
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
          <div className="space-y-4 bg-[#050505] border border-white/10 rounded-3xl p-4 min-h-[400px]">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-white" />
                <h3 className="text-xs sm:text-sm font-bold text-white uppercase tracking-wider">Active PRs</h3>
              </div>
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-[#111111] text-white border border-white/10">
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
          <div className="space-y-4 bg-[#050505] border border-white/10 rounded-3xl p-4 min-h-[400px]">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-neutral-400" />
                <h3 className="text-xs sm:text-sm font-bold text-white uppercase tracking-wider">Needs Attention</h3>
              </div>
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-[#111111] text-white border border-white/10">
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
          <div className="space-y-4 bg-[#050505] border border-white/20 rounded-3xl p-4 min-h-[400px]">
            <div className="flex items-center justify-between border-b border-white/20 pb-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-white animate-pulse" />
                <h3 className="text-xs sm:text-sm font-bold text-white uppercase tracking-wider">Merged Upstream</h3>
              </div>
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-white text-black">
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
    </div>
  );
};

export default PullRequestsView;
