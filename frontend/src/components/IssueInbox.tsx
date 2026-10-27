import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, Filter, ArrowUpDown, Star, GitBranch, Shield, 
  Clock, Zap, CheckCircle, AlertTriangle, ArrowRight, ExternalLink,
  Tag, Info, HelpCircle, Link2, CheckCircle2, XCircle, Plus, Sparkles, ShieldCheck, RefreshCw, Check,
  ArrowUp, Trash2, Calendar
} from 'lucide-react';
import { Issue } from '../types';
import { importIssue, reconcileIssues, triggerDiscoverySync, getCronStatus, triggerCronRunNow, clearInboxIssues } from '../api';

interface IssueInboxProps {
  issues: Issue[];
  loading: boolean;
  totalIssues: number;
  hasMore?: boolean;
  loadingMore?: boolean;
  onLoadMore?: () => void;
  pageSize?: number;
  onPageSizeChange?: (size: number) => void;
  onSelectIssue: (issueId: string) => void;
  onOpenDetails: (issue: Issue) => void;
  onCompleteIssue?: (issueId: string) => Promise<void> | void;
  onFilterChange: (filters: {
    query?: string;
    language?: string;
    difficulty?: string;
    license_status?: string;
    sort_by?: string;
    gsoc_only?: boolean;
    gsoc_org?: string;
  }) => void;
}

export const IssueInbox: React.FC<IssueInboxProps> = ({
  issues,
  loading,
  totalIssues,
  hasMore = false,
  loadingMore = false,
  onLoadMore,
  pageSize = 25,
  onPageSizeChange,
  onSelectIssue,
  onOpenDetails,
  onCompleteIssue,
  onFilterChange,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedLanguage, setSelectedLanguage] = useState('');
  const [selectedDifficulty, setSelectedDifficulty] = useState('');
  const [completingIds, setCompletingIds] = useState<Set<string>>(new Set());
  const [autoLoad, setAutoLoad] = useState(true);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!autoLoad || !hasMore || loadingMore || loading || !onLoadMore) return;

    const observer = new IntersectionObserver((entries) => {
      const first = entries[0];
      if (first.isIntersecting) {
        onLoadMore();
      }
    }, {
      rootMargin: '250px',
      threshold: 0.1,
    });

    const current = sentinelRef.current;
    if (current) observer.observe(current);

    return () => {
      if (current) observer.unobserve(current);
    };
  }, [autoLoad, hasMore, loadingMore, loading, onLoadMore]);

  const handleComplete = async (issueId: string) => {
    if (!onCompleteIssue) return;
    setCompletingIds(prev => new Set(prev).add(issueId));
    try {
      await onCompleteIssue(issueId);
    } finally {
      setCompletingIds(prev => {
        const next = new Set(prev);
        next.delete(issueId);
        return next;
      });
    }
  };
  const [selectedLicense, setSelectedLicense] = useState('');
  const [sortBy, setSortBy] = useState('created');
  const [selectedGsocOrg, setSelectedGsocOrg] = useState('');
  const [isSyncingGsoc, setIsSyncingGsoc] = useState(false);
  const [gsocSyncFeedback, setGsocSyncFeedback] = useState<string | null>(null);

  // 2-Hour Background Cron Job & Inbox Purge State
  const [cronStatus, setCronStatus] = useState<{
    enabled: boolean;
    interval_seconds: number;
    interval_hours: number;
    last_run_at: string | null;
    next_run_at: string | null;
    last_run_status: string;
    last_issues_synced: number;
    last_issues_pruned: number;
    is_running?: boolean;
  } | null>(null);
  const [isClearingInbox, setIsClearingInbox] = useState(false);
  const [isTriggeringCron, setIsTriggeringCron] = useState(false);

  // Live 2-Hour Countdown Timer State (strictly persistent across tab closes, leaves, and reloads)
  const getInitialCountdown = () => {
    try {
      const stored = localStorage.getItem('issuetopr_next_cron_run_at');
      const now = Date.now();
      const targetMs = stored ? new Date(stored).getTime() : 0;
      if (!targetMs || isNaN(targetMs) || targetMs <= now) {
        const newTarget = new Date(now + 7200 * 1000).toISOString();
        localStorage.setItem('issuetopr_next_cron_run_at', newTarget);
        localStorage.setItem('issuetopr_last_cron_run_at', new Date(now).toISOString());
        return 7200;
      }
      return Math.max(0, Math.floor((targetMs - now) / 1000));
    } catch {
      return 7200;
    }
  };

  const [countdownSec, setCountdownSec] = useState<number>(getInitialCountdown);

  const loadCronStatus = async () => {
    try {
      const data = await getCronStatus();
      setCronStatus(data);
    } catch {
      // Ignore background poll errors
    }
  };

  useEffect(() => {
    loadCronStatus();
    const timer = setInterval(loadCronStatus, 15000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const tick = () => {
      let raw = cronStatus?.next_run_at;
      if (!raw) {
        try {
          raw = localStorage.getItem('issuetopr_next_cron_run_at') || undefined;
        } catch {}
      }
      const now = Date.now();
      let target = 0;
      if (raw) {
        const iso = raw.endsWith('Z') || raw.includes('+') ? raw : `${raw}Z`;
        target = new Date(iso).getTime();
      }
      if (!target || isNaN(target) || target <= now) {
        try {
          const newTarget = new Date(now + 7200 * 1000).toISOString();
          localStorage.setItem('issuetopr_next_cron_run_at', newTarget);
          localStorage.setItem('issuetopr_last_cron_run_at', new Date(now).toISOString());
          target = now + 7200 * 1000;
        } catch {}
      }
      const diff = Math.max(0, Math.floor((target - now) / 1000));
      setCountdownSec(diff);

      if (diff === 0 && !isTriggeringCron) {
        loadCronStatus();
      }
    };

    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [cronStatus?.next_run_at, isTriggeringCron]);

  const formatCountdown = (totalSec: number) => {
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    const pad = (n: number) => n.toString().padStart(2, '0');
    return {
      h: pad(h),
      m: pad(m),
      s: pad(s),
      digital: `${pad(h)}:${pad(m)}:${pad(s)}`,
      human: `${h}h ${pad(m)}m ${pad(s)}s`
    };
  };

  const handleClearInbox = async () => {
    if (!window.confirm("Purge all unassigned issues from the inbox? You can then run a fresh scan to populate only current issues.")) return;
    setIsClearingInbox(true);
    setReconcileFeedback(null);
    try {
      const res = await clearInboxIssues();
      setReconcileFeedback(`Purged ${res.deleted_count} issues. Inbox is now clean.`);
      onFilterChange({
        query: searchTerm,
        language: selectedLanguage,
        difficulty: selectedDifficulty,
        license_status: selectedLicense,
        sort_by: sortBy,
        gsoc_org: selectedGsocOrg,
      });
    } catch (err: any) {
      setReconcileFeedback(`Clear error: ${err.message}`);
    } finally {
      setIsClearingInbox(false);
    }
  };

  const handleTriggerCronNow = async () => {
    setIsTriggeringCron(true);
    setGsocSyncFeedback(null);
    try {
      const res = await triggerCronRunNow();
      setGsocSyncFeedback(`✓ 2-Hour Cron scan complete: synced ${res.last_issues_synced} issues, pruned ${res.last_issues_pruned} closed.`);
      await loadCronStatus();
      onFilterChange({
        query: searchTerm,
        language: selectedLanguage,
        difficulty: selectedDifficulty,
        license_status: selectedLicense,
        sort_by: sortBy,
        gsoc_org: selectedGsocOrg,
      });
      setTimeout(() => setGsocSyncFeedback(null), 8000);
    } catch (err: any) {
      setGsocSyncFeedback(`Cron scan error: ${err.message}`);
    } finally {
      setIsTriggeringCron(false);
    }
  };

  const handleSyncGsoc = async () => {
    setIsSyncingGsoc(true);
    setGsocSyncFeedback(null);
    try {
      const res = await triggerDiscoverySync(undefined, true, true);
      const count = res.items_synced || 0;
      setGsocSyncFeedback(`✓ Synced ${count} issues from NumFOCUS, PSF, DeepChem, and Kornia`);
      onFilterChange({
        query: searchTerm,
        language: selectedLanguage,
        difficulty: selectedDifficulty,
        license_status: selectedLicense,
        sort_by: sortBy,
        gsoc_org: selectedGsocOrg,
      });
      setTimeout(() => setGsocSyncFeedback(null), 6000);
    } catch (err: any) {
      setGsocSyncFeedback(`Sync error: ${err.message}`);
    } finally {
      setIsSyncingGsoc(false);
    }
  };

  // Targeted Import & Condition Preflight State
  const [importUrl, setImportUrl] = useState('');
  const [showImportBar, setShowImportBar] = useState(true);
  const [isImporting, setIsImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccessResult, setImportSuccessResult] = useState<{
    meets_all_conditions: boolean;
    conditions_checked: any;
    issue: Issue;
  } | null>(null);

  // Upstream Reconcile & Stale Cleanup State
  const [isReconciling, setIsReconciling] = useState(false);
  const [reconcileFeedback, setReconcileFeedback] = useState<string | null>(null);

  const handleCleanUpstream = async () => {
    setIsReconciling(true);
    setReconcileFeedback(null);
    try {
      const res = await reconcileIssues(true);
      const pruned = (res.reconciled_closed || 0) + (res.purged || 0);
      setReconcileFeedback(`Scanned ${res.checked} issues • Pruned ${pruned} closed/stale • ${res.remaining_open} verified open`);
      onFilterChange({
        query: searchTerm,
        language: selectedLanguage,
        difficulty: selectedDifficulty,
        license_status: selectedLicense,
        sort_by: sortBy,
        gsoc_org: selectedGsocOrg,
      });
    } catch (err: any) {
      setReconcileFeedback(`Reconciliation error: ${err.message}`);
    } finally {
      setIsReconciling(false);
    }
  };

  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importUrl.trim()) return;
    setIsImporting(true);
    setImportError(null);
    setImportSuccessResult(null);

    try {
      const res = await importIssue(importUrl.trim());
      setImportSuccessResult(res);
      if (res.meets_all_conditions) {
        onFilterChange({
          query: searchTerm,
          language: selectedLanguage,
          difficulty: selectedDifficulty,
          license_status: selectedLicense,
          sort_by: sortBy,
          gsoc_org: selectedGsocOrg,
        });
      }
    } catch (err: any) {
      setImportError(err.message || 'Failed to verify and import issue');
    } finally {
      setIsImporting(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onFilterChange({
      query: searchTerm,
      language: selectedLanguage,
      difficulty: selectedDifficulty,
      license_status: selectedLicense,
      sort_by: sortBy,
      gsoc_org: selectedGsocOrg,
    });
  };

  const handleSortChange = (newSort: string) => {
    setSortBy(newSort);
    onFilterChange({
      query: searchTerm,
      language: selectedLanguage,
      difficulty: selectedDifficulty,
      license_status: selectedLicense,
      sort_by: newSort,
      gsoc_org: selectedGsocOrg,
    });
  };

  const getScoreBadgeColor = (score: number) => {
    if (score >= 80) return 'bg-white text-black border-white font-bold shadow-sm';
    if (score >= 65) return 'bg-neutral-900 text-white border-white/30 font-semibold';
    return 'bg-neutral-900 text-neutral-300 border-white/15';
  };

  const getDifficultyBadge = (difficulty: string) => {
    switch (difficulty) {
      case 'beginner':
        return <span className="px-2 py-0.5 rounded-lg text-[11px] font-medium bg-neutral-900 text-neutral-200 border border-white/20">Beginner Friendly</span>;
      case 'advanced':
        return <span className="px-2 py-0.5 rounded-lg text-[11px] font-medium bg-neutral-900 text-neutral-200 border border-white/20">Advanced Scope</span>;
      default:
        return <span className="px-2 py-0.5 rounded-lg text-[11px] font-medium bg-neutral-900 text-neutral-200 border border-white/20">Intermediate</span>;
    }
  };

  const progressPercent = totalIssues > 0 ? Math.min(100, Math.round((issues.length / totalIssues) * 100)) : 100;

  return (
    <div className="space-y-6">
      {/* Targeted Issue Verification & Import Card */}
      <div className="bg-[#080808] border border-white/10 rounded-2xl p-4 sm:p-5 shadow-2xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-white text-black flex items-center justify-center font-bold shrink-0 shadow-md">
              <Sparkles className="w-4 h-4 text-black" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <span>Live Issue Scraper & 7-Point Detection Engine</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-neutral-900 text-neutral-300 border border-white/20">
                  Live GitHub Scraper & Validator
                </span>
              </h3>
              <p className="text-xs text-neutral-400">
                Paste any GitHub issue URL or reference (e.g. https://github.com/mlpack/mlpack/issues/4245 or kubeflow/pipelines#15111) to scrape live, detect assignees, OSI licenses, GSoC eligibility, maintainer policy, and import to your workspace.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setShowImportBar(!showImportBar)}
            className="px-3 py-1.5 rounded-xl text-xs font-medium bg-neutral-900 hover:bg-neutral-800 border border-white/15 text-neutral-200 transition shrink-0 flex items-center gap-1.5 self-start sm:self-auto active:scale-95"
          >
            <Link2 className="w-3.5 h-3.5 text-white" />
            <span>{showImportBar ? 'Collapse' : 'Test / Import Issue URL'}</span>
          </button>
        </div>

        {/* Expandable Import Form */}
        {showImportBar && (
          <form onSubmit={handleImportSubmit} className="pt-3 border-t border-white/10 space-y-3">
            <div className="flex flex-col sm:flex-row gap-2.5">
              <div className="relative flex-1">
                <Link2 className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={importUrl}
                  onChange={(e) => setImportUrl(e.target.value)}
                  placeholder="Paste GitHub issue URL (e.g. https://github.com/pylint-dev/pylint/issues/11713 or pallets/click#2415)..."
                  className="w-full bg-[#000000] border border-white/20 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white focus:ring-1 focus:ring-white font-mono transition"
                />
              </div>
              <button
                type="submit"
                disabled={isImporting || !importUrl.trim()}
                className={`px-5 py-2.5 rounded-xl text-xs font-bold flex items-center justify-center gap-2 transition active:scale-95 ${
                  isImporting || !importUrl.trim()
                    ? 'bg-neutral-900 text-neutral-500 cursor-not-allowed border border-white/10'
                    : 'bg-white hover:bg-neutral-200 text-black shadow-md'
                }`}
              >
                {isImporting ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Checking Conditions...</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>Verify & Import</span>
                  </>
                )}
              </button>
            </div>

            {/* Error Message */}
            {importError && (
              <div className="bg-red-950/40 border border-red-800/60 rounded-xl p-3 text-xs text-red-300 flex items-start gap-2.5">
                <XCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold">Condition Validation Failed: </span>
                  <span>{importError}</span>
                </div>
              </div>
            )}

            {/* Preflight Condition Breakdown Result */}
            {importSuccessResult && (
              <div className={`rounded-xl p-4 border text-xs space-y-3 ${
                importSuccessResult.meets_all_conditions
                  ? 'bg-emerald-950/20 border-emerald-500/40 text-emerald-200'
                  : 'bg-amber-950/20 border-amber-500/40 text-amber-200'
              }`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-semibold">
                    {importSuccessResult.meets_all_conditions ? (
                      <>
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        <span className="text-emerald-300">All Conditions Passed: Issue is Eligible & Added to Inbox!</span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle className="w-4 h-4 text-amber-400" />
                        <span className="text-amber-300">Issue Disqualified (Does Not Meet Set Conditions)</span>
                      </>
                    )}
                  </div>
                  <span className="font-mono text-[11px] text-gray-400">
                    Score: {importSuccessResult.conditions_checked.ranking_score || 50}/100
                  </span>
                </div>

                {/* Condition Pills */}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1 font-mono text-[11px]">
                  <div className="bg-[#0b0f19] px-2.5 py-1.5 rounded-lg border border-gray-800 flex items-center justify-between">
                    <span className="text-gray-400">Issue State:</span>
                    <span className={importSuccessResult.conditions_checked.is_open ? 'text-emerald-400 font-bold' : 'text-red-400 font-bold'}>
                      {importSuccessResult.conditions_checked.is_open ? 'OPEN ✓' : 'CLOSED ✗'}
                    </span>
                  </div>

                  <div className="bg-[#0b0f19] px-2.5 py-1.5 rounded-lg border border-gray-800 flex items-center justify-between">
                    <span className="text-gray-400">Assignees:</span>
                    <span className={importSuccessResult.conditions_checked.is_unassigned ? 'text-emerald-400 font-bold' : 'text-red-400 font-bold'}>
                      {importSuccessResult.conditions_checked.is_unassigned ? '0 (Unassigned) ✓' : 'Already Assigned ✗'}
                    </span>
                  </div>

                  <div className="bg-[#0b0f19] px-2.5 py-1.5 rounded-lg border border-gray-800 flex items-center justify-between">
                    <span className="text-gray-400">License:</span>
                    <span className="text-cyan-400">
                      {importSuccessResult.conditions_checked.license_spdx || 'OSI Verified ✓'}
                    </span>
                  </div>

                  <div className="bg-[#0b0f19] px-2.5 py-1.5 rounded-lg border border-gray-800 flex items-center justify-between">
                    <span className="text-gray-400">Toolbox Match:</span>
                    <span className="text-emerald-400">
                      {importSuccessResult.conditions_checked.skill_match?.length > 0
                        ? importSuccessResult.conditions_checked.skill_match.join(', ')
                        : 'General Scope'}
                    </span>
                  </div>

                  <div className="bg-[#0b0f19] px-2.5 py-1.5 rounded-lg border border-gray-800 flex items-center justify-between">
                    <span className="text-gray-400">Scope Level:</span>
                    <span className="text-purple-400 capitalize">
                      {importSuccessResult.conditions_checked.difficulty_estimate || 'Intermediate'}
                    </span>
                  </div>

                  <div className="bg-[#0b0f19] px-2.5 py-1.5 rounded-lg border border-gray-800 flex items-center justify-between">
                    <span className="text-gray-400">Maintainer Policy:</span>
                    <span className={importSuccessResult.conditions_checked.assignment_required ? 'text-amber-400' : 'text-emerald-400'}>
                      {importSuccessResult.conditions_checked.assignment_required ? 'Assignment Required' : 'Ready to Work'}
                    </span>
                  </div>

                  <div className="bg-[#0b0f19] px-2.5 py-1.5 rounded-lg border border-gray-800 flex items-center justify-between">
                    <span className="text-gray-400">GSoC Status:</span>
                    <span className={importSuccessResult.issue.repository?.is_gsoc ? 'text-amber-300 font-bold' : 'text-gray-400'}>
                      {importSuccessResult.issue.repository?.gsoc_org_name ? `🎓 ${importSuccessResult.issue.repository.gsoc_org_name}` : (importSuccessResult.issue.repository?.is_gsoc ? 'Verified GSoC 🎓' : 'Non-GSoC')}
                    </span>
                  </div>
                </div>

                {/* Reasons or Guidance */}
                {importSuccessResult.conditions_checked.reasons?.length > 0 && (
                  <div className="pt-1 text-[11px] text-gray-300 space-y-1">
                    {importSuccessResult.conditions_checked.reasons.map((r: string, idx: number) => (
                      <p key={idx} className="flex items-center gap-1.5">
                        <span className="text-amber-400">•</span>
                        <span>{r}</span>
                      </p>
                    ))}
                  </div>
                )}

                {/* Action button if eligible */}
                {importSuccessResult.meets_all_conditions && (
                  <div className="pt-2 flex items-center justify-end gap-2">
                    {onCompleteIssue && (
                      <button
                        type="button"
                        onClick={() => {
                          handleComplete(importSuccessResult.issue.id);
                          setImportSuccessResult(null);
                        }}
                        disabled={completingIds.has(importSuccessResult.issue.id)}
                        className="px-3 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-semibold transition flex items-center gap-1.5 active:scale-95 disabled:opacity-50"
                        title="Mark as completed & remove from inbox"
                      >
                        <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                        <span>Done</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => onOpenDetails(importSuccessResult.issue)}
                      className="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium transition"
                    >
                      View Details
                    </button>
                    <button
                      type="button"
                      onClick={() => onSelectIssue(importSuccessResult.issue.id)}
                      className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition shadow-md shadow-emerald-600/30"
                    >
                      Select & Start Working
                    </button>
                  </div>
                )}
              </div>
            )}
          </form>
        )}
      </div>

      {/* Search and Filters Bar */}
      <div className="bg-[#080808] border border-white/10 rounded-2xl p-4 sm:p-5 shadow-2xl">
        <form onSubmit={handleSearchSubmit} className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search open issues by keyword, title, repository (e.g. FastAPI, router, refactor)..."
                className="w-full bg-[#000000] border border-white/20 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-neutral-500 focus:outline-none focus:border-white focus:ring-1 focus:ring-white transition"
              />
            </div>
            <button
              type="submit"
              className="px-5 py-2.5 rounded-xl bg-white hover:bg-neutral-200 text-black font-bold text-sm transition shadow-md active:scale-95 flex items-center justify-center gap-2"
            >
              <Filter className="w-4 h-4" />
              <span>Apply Filters</span>
            </button>
          </div>

          {/* Filter Pills */}
          <div className="flex flex-wrap items-center gap-2.5 sm:gap-3 pt-2 text-xs">
            {/* Language filter */}
            <select
              value={selectedLanguage}
              onChange={(e) => {
                setSelectedLanguage(e.target.value);
                onFilterChange({
                  query: searchTerm,
                  language: e.target.value,
                  difficulty: selectedDifficulty,
                  license_status: selectedLicense,
                  sort_by: sortBy,
                  gsoc_org: selectedGsocOrg,
                });
              }}
              className="bg-[#000000] border border-white/15 rounded-xl px-3 py-1.5 text-neutral-200 focus:outline-none focus:border-white"
            >
              <option value="">All Languages</option>
              <option value="Python">Python</option>
              <option value="TypeScript">TypeScript</option>
              <option value="JavaScript">JavaScript</option>
              <option value="Go">Go</option>
              <option value="Rust">Rust</option>
            </select>

            {/* Difficulty filter */}
            <select
              value={selectedDifficulty}
              onChange={(e) => {
                setSelectedDifficulty(e.target.value);
                onFilterChange({
                  query: searchTerm,
                  language: selectedLanguage,
                  difficulty: e.target.value,
                  license_status: selectedLicense,
                  sort_by: sortBy,
                  gsoc_org: selectedGsocOrg,
                });
              }}
              className="bg-[#000000] border border-white/15 rounded-xl px-3 py-1.5 text-neutral-200 focus:outline-none focus:border-white"
            >
              <option value="">All Difficulties</option>
              <option value="beginner">Beginner Friendly</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
            </select>

            {/* License filter */}
            <select
              value={selectedLicense}
              onChange={(e) => {
                setSelectedLicense(e.target.value);
                onFilterChange({
                  query: searchTerm,
                  language: selectedLanguage,
                  difficulty: selectedDifficulty,
                  license_status: e.target.value,
                  sort_by: sortBy,
                  gsoc_org: selectedGsocOrg,
                });
              }}
              className="bg-[#000000] border border-white/15 rounded-xl px-3 py-1.5 text-neutral-200 focus:outline-none focus:border-white"
            >
              <option value="">All Licenses</option>
              <option value="VERIFIED_OSI">Verified OSI Open-Source</option>
              <option value="UNKNOWN">Needs Review / Unknown</option>
              <option value="NO_LICENSE">No License Detected</option>
            </select>

            {/* 4 Focus Organizations Selector */}
            <div className="flex items-center gap-1.5 py-1 overflow-x-auto no-scrollbar sm:flex-wrap w-full">
              {[
                { id: '', label: 'All 4 Orgs', icon: '🌟' },
                { id: 'numfocus', label: 'NumFOCUS', icon: '🧮' },
                { id: 'psf', label: 'Python (PSF)', icon: '🐍' },
                { id: 'deepchem', label: 'DeepChem', icon: '🧪' },
                { id: 'kornia', label: 'Kornia', icon: '👁️' },
              ].map((org) => {
                const isSelected = selectedGsocOrg === org.id;
                return (
                  <button
                    key={org.id}
                    type="button"
                    onClick={() => {
                      setSelectedGsocOrg(org.id);
                      onFilterChange({
                        query: searchTerm,
                        language: selectedLanguage,
                        difficulty: selectedDifficulty,
                        license_status: selectedLicense,
                        sort_by: sortBy,
                        gsoc_org: org.id,
                      });
                    }}
                    className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 border whitespace-nowrap shadow-sm active:scale-95 ${
                      isSelected
                        ? 'bg-white text-black border-white font-bold shadow-md'
                        : 'bg-[#000000] text-neutral-400 hover:text-white border-white/10 hover:border-white/30'
                    }`}
                  >
                    <span>{org.icon}</span>
                    <span>{org.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Sorting controls */}
            <div className="ml-auto flex items-center gap-1.5 text-neutral-400 flex-wrap">
              <ArrowUpDown className="w-3.5 h-3.5 mr-0.5 text-white" />
              <span>Priority:</span>
              <button
                type="button"
                onClick={() => handleSortChange('created')}
                className={`px-2.5 py-1 rounded-lg transition active:scale-95 ${
                  sortBy === 'created' 
                    ? 'bg-white text-black font-bold shadow-sm' 
                    : 'hover:text-white bg-neutral-900 border border-white/10 text-neutral-300'
                }`}
                title="Priority order is strictly based on time (newest unassigned issues first)"
              >
                🕒 Time (Newest)
              </button>
              <span className="text-neutral-700">|</span>
              <button
                type="button"
                onClick={() => handleSortChange('rank')}
                className={`px-2.5 py-1 rounded-lg transition active:scale-95 ${
                  sortBy === 'rank' 
                    ? 'bg-white text-black font-bold shadow-sm' 
                    : 'hover:text-white text-neutral-400'
                }`}
              >
                Suitability Rank
              </button>
              <span className="text-neutral-700">|</span>
              <button
                type="button"
                onClick={() => handleSortChange('stars')}
                className={`px-2.5 py-1 rounded-lg transition active:scale-95 ${
                  sortBy === 'stars' 
                    ? 'bg-white text-black font-bold shadow-sm' 
                    : 'hover:text-white text-neutral-400'
                }`}
              >
                Stars
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* 2-Hour Autonomous Online Scanner Banner with Live Countdown Timer */}
      <div className="bg-[#080808] border border-white/10 rounded-2xl p-4 sm:p-5 shadow-2xl space-y-3">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 text-xs">
          <div className="flex items-start sm:items-center gap-3">
            <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-white text-black shrink-0 shadow-md">
              <Clock className="w-5 h-5 animate-pulse text-black" />
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-white rounded-full animate-ping" />
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-white rounded-full" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-white font-bold text-sm">2-Hour Autonomous Online Scanner</span>
                <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-neutral-900 text-white border border-white/20 font-mono font-bold flex items-center gap-1.5 shadow-sm">
                  <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
                  {cronStatus?.is_running ? 'SCANNING ONLINE NOW...' : `2H TIMER: ${formatCountdown(countdownSec).digital}`}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-neutral-900 text-neutral-300 border border-white/15 font-mono">
                  Priority: Time-Based
                </span>
              </div>
              <p className="text-neutral-400 text-[11px] pt-1">
                Automatically scans NumFOCUS, Python Software Foundation, DeepChem, and Kornia every 2 hours, ingesting fresh unassigned issues and pruning closed tickets.
              </p>
            </div>
          </div>

          {/* Right section: Live 2-Hour Digital Countdown Display & Controls */}
          <div className="flex flex-wrap items-center gap-3 self-start lg:self-auto">
            {/* Live Countdown Box */}
            <div className="flex items-center gap-2.5 bg-[#000000] border border-white/20 px-3.5 py-1.5 rounded-xl shadow-inner">
              <Clock className="w-4 h-4 text-white animate-pulse" />
              <div className="flex flex-col">
                <span className="text-[9px] uppercase tracking-wider text-neutral-400 font-semibold leading-tight">Next 2h Scan In</span>
                <div className="font-mono text-sm font-extrabold text-white tracking-wider flex items-center gap-1 leading-tight">
                  <span className="bg-neutral-900 px-1.5 py-0.5 rounded border border-white/20">{formatCountdown(countdownSec).h}h</span>
                  <span className="text-neutral-500">:</span>
                  <span className="bg-neutral-900 px-1.5 py-0.5 rounded border border-white/20">{formatCountdown(countdownSec).m}m</span>
                  <span className="text-neutral-500">:</span>
                  <span className="bg-neutral-900 px-1.5 py-0.5 rounded border border-white/20">{formatCountdown(countdownSec).s}s</span>
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={handleTriggerCronNow}
              disabled={isTriggeringCron}
              title="Trigger the 2-Hour scan cycle immediately"
              className="h-10 px-4 rounded-xl bg-white hover:bg-neutral-200 text-black font-bold text-xs flex items-center gap-1.5 shadow-md active:scale-95 transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isTriggeringCron ? 'animate-spin' : ''}`} />
              <span>{isTriggeringCron ? 'Running 2h Scan...' : 'Run 2h Scan Now'}</span>
            </button>

            <button
              type="button"
              onClick={handleClearInbox}
              disabled={isClearingInbox}
              title="Purge all unassigned issues from the database inbox"
              className="h-10 px-3.5 rounded-xl bg-neutral-900 hover:bg-neutral-800 text-neutral-300 hover:text-rose-400 border border-white/15 hover:border-rose-500/40 text-xs font-semibold flex items-center gap-1.5 active:scale-95 transition disabled:opacity-50"
            >
              <Trash2 className={`w-3.5 h-3.5 text-neutral-400 ${isClearingInbox ? 'animate-spin' : ''}`} />
              <span>{isClearingInbox ? 'Purging Issues...' : 'Clear Inbox'}</span>
            </button>
          </div>
        </div>

        {/* Cron Metadata Footer with Live Countdown */}
        {cronStatus && (
          <div className="pt-2.5 border-t border-white/10 flex flex-wrap items-center justify-between gap-2 text-[11px] text-neutral-400 font-mono">
            <div className="flex flex-wrap items-center gap-4">
              <span>
                Last Scan: <strong className="text-white">{cronStatus.last_run_at ? new Date(cronStatus.last_run_at.endsWith('Z') || cronStatus.last_run_at.includes('+') ? cronStatus.last_run_at : `${cronStatus.last_run_at}Z`).toLocaleTimeString() : 'Just now'}</strong>
              </span>
              <span>
                Next Scan: <strong className="text-white">in {formatCountdown(countdownSec).human}</strong>
                <span className="text-neutral-500 text-[10px] ml-1">
                  ({cronStatus.next_run_at ? new Date(cronStatus.next_run_at.endsWith('Z') || cronStatus.next_run_at.includes('+') ? cronStatus.next_run_at : `${cronStatus.next_run_at}Z`).toLocaleTimeString() : 'In 2 hours'})
                </span>
              </span>
              <span>
                Ingested: <strong className="text-white">{cronStatus.last_issues_synced || issues.length}</strong>
              </span>
              <span>
                Status: <strong className="text-white">{cronStatus.is_running ? 'Scanning online...' : 'Every 2 Hours Active'}</strong>
              </span>
            </div>
            <div className="text-neutral-500 text-[10px]">
              Orgs: NumFOCUS • Python (PSF) • DeepChem • Kornia
            </div>
          </div>
        )}
      </div>

      {/* Discovery Counter Notice & Live Upstream Verification */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-gray-400 px-1 py-1 bg-gray-900/40 rounded-xl border border-gray-800/60 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span>
            Showing <span className="font-semibold text-emerald-400">{issues.length}</span> of <span className="font-semibold text-white">{totalIssues.toLocaleString()}</span> issues across <span className="font-semibold text-amber-300">4 Target Orgs</span>
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-300 border border-amber-500/30 text-[10px] font-semibold">
            <span>🎯</span>
            NumFOCUS • PSF • DeepChem • Kornia
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-semibold">
            <ShieldCheck className="w-3 h-3 text-emerald-400" />
            Unassigned & Open Verified
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {gsocSyncFeedback && (
            <span className="text-[11px] text-amber-300 font-medium px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30">
              {gsocSyncFeedback}
            </span>
          )}
          {reconcileFeedback && (
            <span className="text-[11px] text-cyan-400 font-mono">
              {reconcileFeedback}
            </span>
          )}
          <button
            type="button"
            onClick={handleSyncGsoc}
            disabled={isSyncingGsoc}
            title="Scan NumFOCUS, PSF, DeepChem, and Kornia for fresh open unassigned issues"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-amber-500/10 to-orange-500/10 hover:from-amber-500/20 hover:to-orange-500/20 text-amber-300 border border-amber-500/30 hover:border-amber-500/60 text-xs font-semibold transition disabled:opacity-50 shadow-sm"
          >
            <Sparkles className={`w-3.5 h-3.5 text-amber-400 ${isSyncingGsoc ? 'animate-spin' : ''}`} />
            <span>{isSyncingGsoc ? 'Scanning Orgs...' : 'Scan Target Orgs'}</span>
          </button>

          <button
            type="button"
            onClick={handleCleanUpstream}
            disabled={isReconciling}
            title="Scan live GitHub API and remove any issues that have closed or been assigned upstream"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 hover:border-emerald-500/50 text-xs font-medium transition disabled:opacity-50 shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-emerald-400 ${isReconciling ? 'animate-spin' : ''}`} />
            <span>{isReconciling ? 'Verifying Upstream...' : 'Clean Stale / Verify Upstream'}</span>
          </button>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 space-y-3">
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm">Fetching and evaluating open-source opportunities...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && issues.length === 0 && (
        <div className="bg-[#080808] border border-white/10 rounded-2xl p-8 sm:p-12 text-center space-y-4 shadow-2xl">
          <div className="w-12 h-12 rounded-2xl bg-neutral-900 border border-white/15 flex items-center justify-center mx-auto text-white">
            <Search className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold text-white">No matching open issues found</h3>
          <p className="text-xs text-neutral-400 max-w-md mx-auto">
            Try broadening your search query or click "Run 2h Scan Now" above to crawl public repositories for fresh open unassigned issues.
          </p>
        </div>
      )}

      {/* Issue Cards Grid */}
      <div className="grid grid-cols-1 gap-4">
        {issues.map((issue) => {
          const breakdown = issue.ranking_breakdown;
          const isTaskActive = Boolean(issue.active_task);

          return (
            <div
              key={issue.id}
              className="bg-[#080808] border border-white/10 hover:border-white/25 rounded-2xl p-4 sm:p-5 transition-all duration-200 shadow-md hover:-translate-y-0.5 relative group"
            >
              <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
                {/* Left content: repo, issue, badges, description */}
                <div className="space-y-3 flex-1">
                  {/* Repo Pill, Stars, and State */}
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-semibold px-2.5 py-1 rounded-xl bg-neutral-900 border border-white/20 text-white">
                      {issue.repository?.full_name || 'public/repo'}
                    </span>

                    {/* GSoC Participating Organization Badge */}
                    {(issue.repository?.is_gsoc || issue.repository?.gsoc_org_name) && (
                      <span
                        className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-neutral-900 text-neutral-200 border border-white/20 shadow-sm"
                        title={`Verified Google Summer of Code (GSoC) Participating Organization: ${issue.repository?.gsoc_org_name || 'GSoC'}`}
                      >
                        <span className="text-xs">🎓</span>
                        <span>GSoC: {issue.repository?.gsoc_org_name || 'GSoC Org'}</span>
                      </span>
                    )}

                    {issue.repository?.primary_language && (
                      <span className="text-[11px] font-medium px-2 py-0.5 rounded-lg bg-neutral-900 text-neutral-300 border border-white/10">
                        {issue.repository.primary_language}
                      </span>
                    )}

                    <div className="flex items-center gap-1 text-[11px] text-neutral-400 px-2 py-0.5 rounded-lg bg-neutral-900 border border-white/10">
                      <Star className="w-3 h-3 text-white fill-white/20" />
                      <span>{issue.repository?.stars_count?.toLocaleString() || 0}</span>
                    </div>

                    {/* License status indicator */}
                    {issue.license_status === 'VERIFIED_OSI' ? (
                      <span className="flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-lg bg-neutral-900 text-neutral-200 border border-white/20" title="Verified OSI Open-Source License">
                        <Shield className="w-3 h-3" />
                        <span>{issue.repository?.license_spdx || 'OSI License'}</span>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-lg bg-neutral-900 text-neutral-300 border border-white/15" title="License requires inspection before contribution">
                        <AlertTriangle className="w-3 h-3 text-amber-400" />
                        <span>Policy Check Required</span>
                      </span>
                    )}

                    {/* Policy State */}
                    {issue.policy_status === 'ASSIGNMENT_REQUIRED' && (
                      <span className="text-[11px] font-medium px-2 py-0.5 rounded-lg bg-neutral-900 text-neutral-300 border border-white/15">
                        Maintainer Assignment Required
                      </span>
                    )}
                  </div>

                  {/* Title and Link */}
                  <div>
                    <h2 className="text-base font-semibold text-white group-hover:text-neutral-200 transition flex items-center gap-2">
                      <span>#{issue.issue_number} — {issue.title}</span>
                      <a
                        href={issue.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-neutral-500 hover:text-white transition inline-flex items-center"
                        title="View upstream GitHub issue"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    </h2>
                  </div>

                  {/* AI Summary Snippet */}
                  {issue.ai_summary && (
                    <p className="text-xs text-neutral-300 line-clamp-2 leading-relaxed bg-[#020202] p-3 rounded-xl border border-white/10">
                      {issue.ai_summary}
                    </p>
                  )}

                  {/* Badges: difficulty, hours, labels */}
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    {getDifficultyBadge(issue.difficulty_estimate)}
                    <span className="flex items-center gap-1 text-[11px] text-neutral-400 px-2 py-0.5 rounded-lg bg-neutral-900 border border-white/10">
                      <Clock className="w-3 h-3" />
                      <span>~{issue.estimated_effort_hours}h effort</span>
                    </span>

                    {issue.labels?.slice(0, 3).map((lbl: any, idx: number) => {
                      const name = typeof lbl === 'object' ? lbl.name : lbl;
                      return (
                        <span key={idx} className="text-[11px] text-neutral-400 px-2 py-0.5 rounded-lg bg-neutral-900 border border-white/10">
                          {name}
                        </span>
                      );
                    })}
                  </div>
                </div>

                {/* Right score & Action button */}
                <div className="flex lg:flex-col items-center lg:items-end justify-between lg:justify-start gap-3 border-t lg:border-t-0 pt-3 lg:pt-0 border-white/10">
                  {/* Suitability Score Gauge */}
                  <div className="text-right">
                    <div className="flex items-center gap-1.5 justify-end">
                      <Zap className="w-3.5 h-3.5 text-white" />
                      <span className="text-xs text-neutral-400 font-medium">Suitability</span>
                    </div>
                    <div className="flex items-baseline gap-1 mt-0.5">
                      <span className={`text-2xl font-bold px-2 py-0.5 rounded-xl border ${getScoreBadgeColor(issue.ranking_score)}`}>
                        {issue.ranking_score.toFixed(0)}
                      </span>
                      <span className="text-xs text-neutral-500 font-mono">/100</span>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center gap-2">
                    {onCompleteIssue && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleComplete(issue.id);
                        }}
                        disabled={completingIds.has(issue.id)}
                        title="Mark as completed & remove from inbox"
                        className="px-2.5 py-1.5 rounded-xl bg-neutral-900 hover:bg-neutral-800 text-neutral-300 hover:text-white border border-white/15 hover:border-white/30 text-xs font-semibold transition-all flex items-center gap-1.5 active:scale-95 disabled:opacity-50 group/tick"
                      >
                        <Check className="w-3.5 h-3.5 stroke-[2.5] text-white group-hover/tick:scale-110 transition-transform" />
                        <span className="hidden sm:inline">Done</span>
                      </button>
                    )}

                    <button
                      onClick={() => onOpenDetails(issue)}
                      className="px-3 py-1.5 rounded-xl bg-neutral-900 hover:bg-neutral-800 text-neutral-300 hover:text-white text-xs font-medium border border-white/15 transition active:scale-95"
                    >
                      Details & Rationale
                    </button>

                    <button
                      onClick={() => onSelectIssue(issue.id)}
                      className="px-4 py-1.5 rounded-xl bg-white hover:bg-neutral-200 text-black text-xs font-bold shadow-md active:scale-95 transition flex items-center gap-1.5"
                    >
                      <span>{isTaskActive ? 'Resume Task' : 'Select Issue'}</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Explainable reasons pills */}
              {breakdown?.reasons && breakdown.reasons.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-800/60 flex flex-wrap gap-2 text-[11px] text-gray-400">
                  <span className="text-gray-500 font-medium">Scoring factors:</span>
                  {breakdown.reasons.slice(0, 3).map((r: string, idx: number) => (
                    <span key={idx} className="bg-gray-900/90 px-2 py-0.5 rounded border border-gray-800/70 text-gray-300">
                      • {r}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Load More & Infinite Scroll Section */}
      {!loading && issues.length > 0 && (
        <div className="bg-[#111827] border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-gray-800/80">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white">Issues Explorer Progress</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800/40 font-mono">
                  {issues.length} / {totalIssues.toLocaleString()} Loaded ({progressPercent}%)
                </span>
              </div>
              <p className="text-[11px] text-gray-400 mt-0.5">
                {hasMore 
                  ? `${(totalIssues - issues.length).toLocaleString()} more public issues match your criteria` 
                  : 'All available matching issues have been loaded'}
              </p>
            </div>

            <div className="flex items-center gap-3 text-xs">
              {/* Batch Size Selector */}
              <div className="flex items-center gap-1.5 bg-[#0b0f19] border border-gray-800 rounded-xl px-2.5 py-1">
                <span className="text-gray-400 text-[11px]">Batch:</span>
                {[25, 50, 100].map(size => (
                  <button
                    key={size}
                    type="button"
                    onClick={() => onPageSizeChange && onPageSizeChange(size)}
                    className={`px-2 py-0.5 rounded-lg text-xs font-medium transition ${
                      pageSize === size
                        ? 'bg-emerald-500/20 text-emerald-300 font-bold'
                        : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {size}
                  </button>
                ))}
              </div>

              {/* Auto Load Switch */}
              <button
                type="button"
                onClick={() => setAutoLoad(!autoLoad)}
                className={`px-3 py-1 rounded-xl border text-xs font-semibold transition flex items-center gap-1.5 ${
                  autoLoad
                    ? 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
                    : 'bg-gray-800 text-gray-400 border-gray-700 hover:text-white'
                }`}
                title="Automatically fetch next batch when scrolling near the bottom"
              >
                <span className={`w-2 h-2 rounded-full ${autoLoad ? 'bg-cyan-400 animate-pulse' : 'bg-gray-500'}`} />
                <span>Auto-load: {autoLoad ? 'ON' : 'OFF'}</span>
              </button>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="w-full bg-[#0b0f19] rounded-full h-2 overflow-hidden border border-gray-800">
            <div 
              className="bg-gradient-to-r from-emerald-500 to-cyan-500 h-full transition-all duration-300 rounded-full"
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          {/* Action button */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
            {hasMore ? (
              <button
                type="button"
                onClick={onLoadMore}
                disabled={loadingMore}
                className="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 text-white font-bold text-xs shadow-lg shadow-emerald-950/40 active:scale-95 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {loadingMore ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Loading next batch of issues...</span>
                  </>
                ) : (
                  <>
                    <Plus className="w-4 h-4" />
                    <span>Load More Issues (+{pageSize || 25})</span>
                    <span className="text-[11px] opacity-80 font-normal">
                      ({(totalIssues - issues.length).toLocaleString()} remaining)
                    </span>
                  </>
                )}
              </button>
            ) : (
              <div className="py-2 text-center text-xs text-gray-400 flex items-center justify-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>All {totalIssues.toLocaleString()} open unassigned issues loaded cleanly.</span>
              </div>
            )}
          </div>

          {/* Invisible intersection sentinel for auto-load */}
          {hasMore && <div ref={sentinelRef} className="h-6 w-full pointer-events-none" />}
        </div>
      )}

      {/* Floating Back-to-Top Button */}
      {issues.length > 20 && (
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="fixed bottom-6 left-6 z-40 px-3.5 py-2 rounded-2xl bg-[#111827]/90 hover:bg-[#1f2937] text-gray-300 hover:text-white border border-gray-700/80 shadow-2xl backdrop-blur-md text-xs font-semibold transition flex items-center gap-1.5 active:scale-95"
          title="Scroll back to top"
        >
          <ArrowUp className="w-3.5 h-3.5 text-cyan-400" />
          <span>Back to Top</span>
        </button>
      )}
    </div>
  );
};
