import React, { useState, useMemo } from 'react';
import { 
  Plus, ExternalLink, RefreshCw, Trash2, GitPullRequest, 
  AlertCircle, CheckCircle2, Clock, MessageSquare, AlertTriangle,
  FolderGit2, Check, User, Search, Sparkles, ArrowUpDown
} from 'lucide-react';
import { Task } from '../types';

interface TrackedIssuesViewProps {
  tasks: Task[];
  onTrackUrl: (url: string) => Promise<void>;
  onSyncItem: (taskId: string) => Promise<void>;
  onUntrackItem: (taskId: string) => Promise<void>;
  onImportAuthorPRs?: (username?: string) => Promise<void>;
}

type SortField = 'updated' | 'repo' | 'number' | 'status';

export const TrackedIssuesView: React.FC<TrackedIssuesViewProps> = ({
  tasks,
  onTrackUrl,
  onSyncItem,
  onUntrackItem,
  onImportAuthorPRs,
}) => {
  const [inputUrl, setInputUrl] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<'all' | 'prs' | 'issues'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortField>('updated');
  const [sortAsc, setSortAsc] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputUrl.trim()) return;

    setIsAdding(true);
    setErrorMsg(null);
    try {
      await onTrackUrl(inputUrl.trim());
      setInputUrl('');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to track item.');
    } finally {
      setIsAdding(false);
    }
  };

  const handleImportClick = async () => {
    if (!onImportAuthorPRs) return;
    setIsImporting(true);
    setErrorMsg(null);
    try {
      await onImportAuthorPRs();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to import PRs.');
    } finally {
      setIsImporting(false);
    }
  };

  const handleSyncClick = async (taskId: string) => {
    setSyncingId(taskId);
    try {
      await onSyncItem(taskId);
    } finally {
      setSyncingId(null);
    }
  };

  // Filter and sort items
  const sortedAndFilteredTasks = useMemo(() => {
    const filtered = tasks.filter(t => {
      if (filterType === 'prs' && !t.pr_number && !t.pr_url) return false;
      if (filterType === 'issues' && (t.pr_number || t.pr_url)) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const titleMatch = t.issue?.title?.toLowerCase().includes(q);
        const repoMatch = t.issue?.repository?.full_name?.toLowerCase().includes(q);
        const numberMatch = t.issue?.issue_number?.toString().includes(q) || t.pr_number?.toString().includes(q);
        return titleMatch || repoMatch || numberMatch;
      }
      return true;
    });

    return filtered.sort((a, b) => {
      let comparison = 0;
      if (sortBy === 'updated') {
        const timeA = new Date(a.updated_at || a.created_at || 0).getTime();
        const timeB = new Date(b.updated_at || b.created_at || 0).getTime();
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
  }, [tasks, filterType, searchQuery, sortBy, sortAsc]);

  const totalPRs = tasks.filter(t => Boolean(t.pr_number || t.pr_url)).length;
  const mergedPRs = tasks.filter(t => t.pr_merged).length;
  const totalIssues = tasks.filter(t => !t.pr_number && !t.pr_url).length;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Quick Add Bar */}
      <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-5 sm:p-6 shadow-xl relative overflow-hidden">
        <div className="max-w-3xl space-y-3 relative z-10">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-ping" />
            <span className="text-xs font-bold text-blue-600 dark:text-blue-400 uppercase tracking-wider">Universal GitHub Tracker</span>
          </div>
          <h2 className="text-xl font-extrabold text-slate-900 dark:text-white">Track an Issue or Pull Request</h2>
          <p className="text-xs text-slate-500 dark:text-neutral-400">
            Paste any GitHub Issue or Pull Request URL to monitor its live status, CI check runs, assignments, and maintainer review comments in real-time.
          </p>

          <form onSubmit={handleAddSubmit} className="pt-2 flex flex-col sm:flex-row gap-2.5">
            <div className="relative flex-1">
              <input
                type="text"
                value={inputUrl}
                onChange={(e) => setInputUrl(e.target.value)}
                placeholder="https://github.com/owner/repo/pull/123 or https://github.com/owner/repo/issues/456"
                className="w-full bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-4 py-2.5 text-xs text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition font-mono"
              />
            </div>
            <button
              type="submit"
              disabled={isAdding || !inputUrl.trim()}
              className="px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:hover:bg-neutral-200 dark:text-black font-bold text-xs shadow-md active:scale-95 transition flex items-center justify-center gap-2 disabled:opacity-50 shrink-0"
            >
              <Plus className={`w-4 h-4 ${isAdding ? 'animate-spin' : ''}`} />
              <span>{isAdding ? 'Fetching...' : '+ Track Item'}</span>
            </button>

            {onImportAuthorPRs && (
              <button
                type="button"
                onClick={handleImportClick}
                disabled={isImporting}
                className="px-4 py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-200 dark:bg-white/5 dark:hover:bg-white/10 dark:text-white dark:border-white/10 font-bold text-xs shadow-sm active:scale-95 transition flex items-center justify-center gap-1.5 disabled:opacity-50 shrink-0"
                title="Automatically import all PRs authored by you from GitHub"
              >
                <Sparkles className={`w-4 h-4 text-slate-600 dark:text-neutral-300 ${isImporting ? 'animate-spin' : ''}`} />
                <span>{isImporting ? 'Importing...' : 'Import My PRs'}</span>
              </button>
            )}
          </form>

          {errorMsg && (
            <div className="p-3 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-500/30 rounded-xl text-xs text-rose-700 dark:text-rose-300 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}
        </div>
      </div>

      {/* Stats Counter Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-4 space-y-1 shadow-sm dark:shadow-lg">
          <span className="text-[11px] text-slate-500 dark:text-neutral-400 font-semibold uppercase tracking-wider block">Total Tracked</span>
          <span className="text-2xl font-black text-slate-900 dark:text-white">{tasks.length}</span>
        </div>
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-4 space-y-1 shadow-sm dark:shadow-lg">
          <span className="text-[11px] text-slate-500 dark:text-neutral-400 font-semibold uppercase tracking-wider block">Active PRs</span>
          <span className="text-2xl font-black text-slate-900 dark:text-white">{totalPRs - mergedPRs}</span>
        </div>
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-4 space-y-1 shadow-sm dark:shadow-lg">
          <span className="text-[11px] text-slate-500 dark:text-neutral-400 font-semibold uppercase tracking-wider block">Merged PRs</span>
          <span className="text-2xl font-black text-slate-900 dark:text-white">{mergedPRs}</span>
        </div>
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-4 space-y-1 shadow-sm dark:shadow-lg">
          <span className="text-[11px] text-slate-500 dark:text-neutral-400 font-semibold uppercase tracking-wider block">Monitored Issues</span>
          <span className="text-2xl font-black text-slate-900 dark:text-white">{totalIssues}</span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-3 shadow-sm dark:shadow-lg">
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-semibold">
          <button
            onClick={() => setFilterType('all')}
            className={`px-3 py-1.5 rounded-xl transition active:scale-95 ${
              filterType === 'all' || filterType === 'prs'
                ? 'bg-slate-900 text-white dark:bg-white dark:text-black font-bold shadow-sm'
                : 'text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 dark:text-neutral-400 dark:hover:text-white dark:bg-white/5 dark:hover:bg-white/10'
            }`}
          >
            Pull Requests ({totalPRs})
          </button>
          {totalIssues > 0 && (
            <button
              onClick={() => setFilterType('issues')}
              className={`px-3 py-1.5 rounded-xl transition active:scale-95 ${
                filterType === 'issues'
                  ? 'bg-slate-900 text-white dark:bg-white dark:text-black font-bold shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 dark:text-neutral-400 dark:hover:text-white dark:bg-white/5 dark:hover:bg-white/10'
              }`}
            >
              Issues ({totalIssues})
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Sort Selector */}
          <div className="flex items-center gap-1 bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl p-1 text-xs">
            <span className="text-slate-500 dark:text-neutral-500 px-1 text-[11px] flex items-center gap-1">
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
              <option value="number" className="bg-white dark:bg-[#0c101a] text-slate-900 dark:text-white">PR / Issue #</option>
              <option value="status" className="bg-white dark:bg-[#0c101a] text-slate-900 dark:text-white">Status Priority</option>
            </select>
            <button
              onClick={() => setSortAsc(!sortAsc)}
              className="p-1 text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white rounded transition"
              title={sortAsc ? 'Ascending' : 'Descending'}
            >
              {sortAsc ? '↑' : '↓'}
            </button>
          </div>

          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 dark:text-neutral-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search repo, title, #..."
              className="bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl pl-8 pr-3 py-1.5 text-xs text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-neutral-500 focus:outline-none focus:border-blue-500 w-36 sm:w-48 transition"
            />
          </div>
        </div>
      </div>

      {/* Cards List */}
      {sortedAndFilteredTasks.length === 0 ? (
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-8 sm:p-12 text-center space-y-3 shadow-sm dark:shadow-xl">
          <FolderGit2 className="w-8 h-8 text-slate-400 dark:text-neutral-500 mx-auto" />
          <h3 className="text-base font-bold text-slate-900 dark:text-white">No items found</h3>
          <p className="text-xs text-slate-500 dark:text-neutral-400 max-w-sm mx-auto">
            Paste any GitHub pull request or issue URL into the box above to start live tracking.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {sortedAndFilteredTasks.map((task) => {
            const isPR = Boolean(task.pr_number || task.pr_url);
            const isMerged = task.pr_merged;
            const isClosed = task.issue?.state === 'closed' || task.pr_state === 'closed';

            return (
              <div
                key={task.id}
                className={`bg-[#0c101a] border rounded-2xl p-4 sm:p-5 shadow-xl space-y-4 transition-all duration-200 hover:-translate-y-0.5 hover:bg-[#0f1422] ${
                  isMerged
                    ? 'border-purple-500/30 hover:border-purple-500/50'
                    : 'border-white/10 hover:border-white/25'
                }`}
              >
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs px-2.5 py-0.5 rounded-lg bg-white/5 border border-white/10 text-emerald-400 font-semibold truncate max-w-[220px]">
                        {task.issue?.repository?.full_name || 'Repository'}
                      </span>

                      {isPR ? (
                        <span className="text-xs font-bold text-purple-400 flex items-center gap-1 font-mono">
                          <GitPullRequest className="w-3.5 h-3.5" />
                          <span>PR #{task.pr_number}</span>
                        </span>
                      ) : (
                        <span className="text-xs text-neutral-400 font-mono">
                          Issue #{task.issue?.issue_number}
                        </span>
                      )}

                      {/* State Badge */}
                      {isMerged ? (
                        <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 flex items-center gap-1">
                          <Sparkles className="w-3 h-3 text-purple-400" />
                          <span>MERGED UPSTREAM</span>
                        </span>
                      ) : isClosed ? (
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-white/5 text-neutral-400 border border-white/10">
                          CLOSED
                        </span>
                      ) : (
                        <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          OPEN
                        </span>
                      )}

                      {/* Review Status Badge if PR */}
                      {isPR && task.pr_review_status && task.pr_review_status !== 'PENDING' && (
                        <span className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full border ${
                          task.pr_review_status === 'APPROVED' ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' :
                          task.pr_review_status === 'CHANGES_REQUESTED' ? 'bg-rose-500/20 text-rose-300 border-rose-500/30' :
                          'bg-blue-500/20 text-blue-300 border-blue-500/30'
                        }`}>
                          {task.pr_review_status.replace(/_/g, ' ')}
                        </span>
                      )}

                      {/* CI Status Badge if PR */}
                      {isPR && task.pr_ci_status && (
                        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-lg border flex items-center gap-1 ${
                          task.pr_ci_status === 'success' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                          task.pr_ci_status === 'failure' ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' :
                          'bg-amber-500/10 text-amber-400 border-amber-500/20'
                        }`}>
                          {task.pr_ci_status === 'success' ? <CheckCircle2 className="w-3 h-3" /> :
                           task.pr_ci_status === 'failure' ? <AlertCircle className="w-3 h-3" /> :
                           <Clock className="w-3 h-3 animate-spin" />}
                          <span>CI: {task.pr_ci_status.toUpperCase()}</span>
                        </span>
                      )}
                    </div>

                    <h3 className="text-base font-bold text-white">
                      {task.issue?.title}
                    </h3>

                    {/* Metadata & Quick Links */}
                    <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                      {task.issue?.html_url && (
                        <a
                          href={task.issue.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 hover:border-white/20 text-neutral-300 hover:text-white flex items-center gap-1 transition"
                        >
                          <span>{isPR ? `PR #${task.pr_number}` : `Issue #${task.issue.issue_number}`}</span>
                          <ExternalLink className="w-3 h-3 text-neutral-400" />
                        </a>
                      )}

                      {task.pr_url && task.pr_url !== task.issue?.html_url && (
                        <a
                          href={task.pr_url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg bg-purple-950/40 border border-purple-500/30 hover:bg-purple-900/50 text-purple-300 flex items-center gap-1.5 transition font-semibold"
                        >
                          <GitPullRequest className="w-3 h-3 text-purple-400" />
                          <span>Pull Request</span>
                          <ExternalLink className="w-3 h-3 text-purple-400/80" />
                        </a>
                      )}

                      {task.assignment_comment_id && (
                        <a
                          href={task.assignment_comment_id.startsWith('http') ? task.assignment_comment_id : `${task.issue?.html_url}#issuecomment-${task.assignment_comment_id}`}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg bg-cyan-950/40 border border-cyan-500/30 hover:bg-cyan-900/50 text-cyan-300 flex items-center gap-1.5 transition font-medium"
                        >
                          <MessageSquare className="w-3 h-3 text-cyan-400" />
                          <span>Assignment Comment</span>
                          <ExternalLink className="w-3 h-3 text-cyan-400/80" />
                        </a>
                      )}

                      {task.issue?.author && (
                        <span className="text-neutral-400 flex items-center gap-1 pl-1 text-[11px]">
                          <User className="w-3 h-3" />
                          <span>@{task.issue.author}</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions: Sync & Untrack */}
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleSyncClick(task.id)}
                      disabled={syncingId === task.id}
                      className="px-3.5 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-neutral-200 hover:text-white text-xs font-semibold border border-white/10 transition flex items-center gap-1.5 active:scale-95"
                      title="Sync live state with GitHub"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${syncingId === task.id ? 'animate-spin' : ''}`} />
                      <span>{syncingId === task.id ? 'Syncing...' : 'Sync Live'}</span>
                    </button>

                    <button
                      onClick={() => onUntrackItem(task.id)}
                      className="p-1.5 rounded-xl text-neutral-400 hover:text-rose-400 hover:bg-rose-950/20 border border-transparent hover:border-rose-500/20 transition"
                      title="Remove from tracking"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* If PR Review comments exist, show expandable preview */}
                {isPR && task.pr_review_comments && task.pr_review_comments.length > 0 && (
                  <div className="bg-[#05080f] border border-white/10 rounded-xl p-3 space-y-2">
                    <span className="text-[11px] font-semibold text-neutral-400 uppercase tracking-wider block">
                      Maintainer Reviews ({task.pr_review_comments.length})
                    </span>
                    <div className="space-y-1.5">
                      {task.pr_review_comments.slice(0, 2).map((rev, idx) => (
                        <div key={idx} className="text-xs bg-[#0c101a] p-2.5 rounded-lg border border-white/10 flex items-start justify-between gap-2">
                          <div>
                            <span className="font-semibold text-neutral-200">@{rev.author}</span>: {rev.body || 'Submitted review.'}
                          </div>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                            rev.state === 'APPROVED' ? 'bg-emerald-500/20 text-emerald-300' :
                            rev.state === 'CHANGES_REQUESTED' ? 'bg-rose-500/20 text-rose-300' :
                            'bg-white/10 text-neutral-400'
                          }`}>
                            {rev.state}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default TrackedIssuesView;
