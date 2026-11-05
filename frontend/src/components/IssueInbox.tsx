import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, Filter, ArrowUpDown, Star, GitBranch, Shield, 
  Clock, Zap, CheckCircle, AlertTriangle, ArrowRight, ExternalLink,
  Tag, Info, HelpCircle, Link2, CheckCircle2, XCircle, Plus, Sparkles, ShieldCheck, RefreshCw, Check,
  ArrowUp, Trash2, Calendar, Building2, Globe, X, Loader2, ChevronDown, ChevronUp
} from 'lucide-react';
import { Issue } from '../types';
import { 
  importIssue, 
  reconcileIssues, 
  triggerDiscoverySync, 
  getCronStatus, 
  triggerCronRunNow, 
  clearInboxIssues, 
  isIssueCompleted,
  getWebsiteInternalSchedule,
  formatCountdownSec,
  TWO_HOURS_SEC,
  fetchTrackedOrganizations,
  addOrganizationByUrl,
  TrackedOrganization
} from '../api';

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
    unassigned_only?: boolean;
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
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [showBackToTop, setShowBackToTop] = useState(false);
  const [completingIds, setCompletingIds] = useState<Set<string>>(new Set());
  const [autoLoad, setAutoLoad] = useState(true);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // Scroll position listener for floating Back-to-Top button
  useEffect(() => {
    const handleScrollPos = () => {
      const scrollY = window.scrollY || document.documentElement.scrollTop;
      setShowBackToTop(scrollY > 400);
    };
    window.addEventListener('scroll', handleScrollPos, { passive: true });
    return () => window.removeEventListener('scroll', handleScrollPos);
  }, []);

  // Dual-trigger infinite auto-load (IntersectionObserver + window scroll fallback)
  useEffect(() => {
    if (!autoLoad || !hasMore || loadingMore || loading || !onLoadMore) return;

    // 1. IntersectionObserver with prefetch rootMargin
    const observer = new IntersectionObserver((entries) => {
      const first = entries[0];
      if (first.isIntersecting && !loadingMore && hasMore) {
        onLoadMore();
      }
    }, {
      rootMargin: '800px 0px',
      threshold: 0,
    });

    const current = sentinelRef.current;
    if (current) observer.observe(current);

    // 2. Window Scroll and Resize event listener
    const handleScrollOrResize = () => {
      if (!autoLoad || !hasMore || loadingMore || loading) return;
      const scrollHeight = document.documentElement.scrollHeight;
      const scrollTop = window.scrollY || document.documentElement.scrollTop;
      const clientHeight = window.innerHeight;
      if (scrollHeight - (scrollTop + clientHeight) < 800) {
        onLoadMore();
      }
    };

    window.addEventListener('scroll', handleScrollOrResize, { passive: true });
    window.addEventListener('resize', handleScrollOrResize, { passive: true });

    // 3. Viewport fill check: If issues don't fill tall screen, trigger next page
    const timer = setTimeout(() => {
      if (document.documentElement.scrollHeight <= window.innerHeight + 200) {
        handleScrollOrResize();
      }
    }, 300);

    return () => {
      clearTimeout(timer);
      if (current) observer.unobserve(current);
      window.removeEventListener('scroll', handleScrollOrResize);
      window.removeEventListener('resize', handleScrollOrResize);
    };
  }, [autoLoad, hasMore, loadingMore, loading, onLoadMore]);

  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set());

  const handleComplete = async (issueId: string) => {
    if (!onCompleteIssue) return;
    setCompletedIds(prev => new Set(prev).add(issueId));
    setCompletingIds(prev => new Set(prev).add(issueId));
    try {
      await onCompleteIssue(issueId);
    } catch {
      setCompletedIds(prev => {
        const next = new Set(prev);
        next.delete(issueId);
        return next;
      });
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

  // 2-Hour Website Internal Autonomous Engine State
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
  }>(() => {
    const s = getWebsiteInternalSchedule();
    return {
      enabled: true,
      interval_seconds: TWO_HOURS_SEC,
      interval_hours: 2,
      last_run_at: s.last_run_at,
      next_run_at: s.next_run_at,
      last_run_status: 'success',
      last_issues_synced: 421,
      last_issues_pruned: 0,
      is_running: false,
    };
  });
  const [isClearingInbox, setIsClearingInbox] = useState(false);
  const [isTriggeringCron, setIsTriggeringCron] = useState(false);

  // Live 2-Hour Countdown Timer State (runs autonomously across tabs and sessions)
  const [countdownSec, setCountdownSec] = useState<number>(() => {
    return getWebsiteInternalSchedule().countdown_sec;
  });

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
      const now = Date.now();
      let targetMs = 0;
      if (cronStatus?.next_run_at) {
        const raw = cronStatus.next_run_at;
        const iso = raw.endsWith('Z') || raw.includes('+') ? raw : `${raw}Z`;
        targetMs = new Date(iso).getTime();
      }

      if (!targetMs || isNaN(targetMs) || targetMs <= now) {
        // Fall back directly to website internal deterministic schedule
        const currentSchedule = getWebsiteInternalSchedule();
        setCountdownSec(currentSchedule.countdown_sec);

        if (currentSchedule.countdown_sec === 0 && !isTriggeringCron) {
          loadCronStatus();
        }
      } else {
        const diff = Math.max(0, Math.floor((targetMs - now) / 1000));
        setCountdownSec(diff);

        if (diff === 0 && !isTriggeringCron) {
          loadCronStatus();
        }
      }
    };

    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [cronStatus?.next_run_at, isTriggeringCron]);

  const formatCountdown = (totalSec: number) => {
    return formatCountdownSec(totalSec);
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

  // Dynamic Tracked Organizations & + Add Org State
  const [trackedOrgs, setTrackedOrgs] = useState<TrackedOrganization[]>([
    { id: 'numfocus', label: 'NumFOCUS', icon: '🧮', is_default: true, issue_count: 372 },
    { id: 'psf', label: 'Python (PSF)', icon: '🐍', is_default: true, issue_count: 244 },
    { id: 'deepchem', label: 'DeepChem', icon: '🧪', is_default: true, issue_count: 37 },
    { id: 'kornia', label: 'Kornia', icon: '👁️', is_default: true, issue_count: 69 },
    { id: 'noruzzamans/gslider-blocks', label: 'noruzzamans/gslider-blocks', icon: '📦', is_default: false, issue_count: 0 },
    { id: 'Pushkar-Shahi/Mirador', label: 'Pushkar-Shahi/Mira...', icon: '📦', is_default: false, issue_count: 0 },
  ]);
  const [isAddOrgModalOpen, setIsAddOrgModalOpen] = useState(false);
  const [addOrgUrl, setAddOrgUrl] = useState('');
  const [addOrgName, setAddOrgName] = useState('');
  const [isAddingOrg, setIsAddingOrg] = useState(false);
  const [addOrgSuccess, setAddOrgSuccess] = useState<string | null>(null);
  const [addOrgError, setAddOrgError] = useState<string | null>(null);

  const loadTrackedOrgs = async () => {
    try {
      const data = await fetchTrackedOrganizations();
      if (data && data.organizations && data.organizations.length > 0) {
        setTrackedOrgs(prev => {
          const apiMap = new Map<string, TrackedOrganization>(
            data.organizations.map((o: TrackedOrganization) => [o.id.toLowerCase(), o])
          );
          const updated = prev.map(p => {
            const match = apiMap.get(p.id.toLowerCase());
            return match ? { ...p, issue_count: match.issue_count || p.issue_count } : p;
          });
          for (const org of data.organizations) {
            if (!prev.some(p => p.id.toLowerCase() === org.id.toLowerCase())) {
              updated.push(org);
            }
          }
          return updated;
        });
      }
    } catch (e) {
      console.warn('Failed to load tracked organizations', e);
    }
  };

  useEffect(() => {
    loadTrackedOrgs();
  }, []);

  const handleAddOrgSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addOrgUrl.trim()) return;
    setIsAddingOrg(true);
    setAddOrgError(null);
    setAddOrgSuccess(null);
    try {
      const res = await addOrganizationByUrl(addOrgUrl.trim(), addOrgName.trim() || undefined);
      setAddOrgSuccess(res.message);
      await loadTrackedOrgs();
      // Select the newly added organization and reload issues
      const targetId = res.owner.toLowerCase();
      setSelectedGsocOrg(targetId);
      onFilterChange({
        query: searchTerm,
        language: selectedLanguage,
        difficulty: selectedDifficulty,
        license_status: selectedLicense,
        sort_by: sortBy,
        gsoc_org: targetId,
      });
      setTimeout(() => {
        setIsAddOrgModalOpen(false);
        setAddOrgSuccess(null);
        setAddOrgUrl('');
        setAddOrgName('');
      }, 1500);
    } catch (err: any) {
      setAddOrgError(err.message || 'Failed to add organization');
    } finally {
      setIsAddingOrg(false);
    }
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

  const visibleIssues = issues.filter(i => !completedIds.has(i.id) && !isIssueCompleted(i));
  const progressPercent = totalIssues > 0 ? Math.min(100, Math.round((visibleIssues.length / totalIssues) * 100)) : 100;

  return (
    <div className="space-y-6">
      {/* Top Header Row with Page Title on Left and 2H Countdown + Scan Button on Right */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Issue-to-PR
          </h1>
          <p className="text-xs text-neutral-400">
            Find issues, filter smartly, and turn them into pull requests.
          </p>
        </div>

        {/* Top Right Live Countdown + Run 2h Scan Now */}
        <div className="flex items-center gap-3">
          {/* Live Countdown Box */}
          <div className="flex items-center gap-2.5 bg-[#0c101a] border border-white/10 px-3.5 py-2 rounded-2xl shadow-lg">
            <Clock className="w-4 h-4 text-neutral-400" />
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase font-mono tracking-wider text-neutral-400 font-bold">
                NEXT 2H SCAN IN
              </span>
              <div className="font-mono text-xs font-bold text-white flex items-center gap-1">
                <span className="bg-[#05080f] px-1.5 py-0.5 rounded border border-white/10">
                  {formatCountdown(countdownSec).h}h
                </span>
                <span className="text-neutral-500">:</span>
                <span className="bg-[#05080f] px-1.5 py-0.5 rounded border border-white/10">
                  {formatCountdown(countdownSec).m}m
                </span>
                <span className="text-neutral-500">:</span>
                <span className="bg-[#05080f] px-1.5 py-0.5 rounded border border-white/10">
                  {formatCountdown(countdownSec).s}s
                </span>
              </div>
            </div>
          </div>

          {/* Solid White Run 2h Scan Now Button */}
          <button
            type="button"
            onClick={handleTriggerCronNow}
            disabled={isTriggeringCron}
            title="Run 2-Hour Autonomous Scan Now"
            className="px-4 py-2.5 rounded-2xl bg-white hover:bg-neutral-200 text-black font-bold text-xs flex items-center gap-2 shadow-md active:scale-95 transition disabled:opacity-50 shrink-0"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isTriggeringCron ? 'animate-spin' : ''}`} />
            <span>{isTriggeringCron ? 'Scanning...' : 'Run 2h Scan Now'}</span>
          </button>
        </div>
      </div>

      {/* Targeted Issue Verification & Import Card */}
      <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-4 sm:p-5 shadow-xl space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-white shrink-0">
              <Link2 className="w-5 h-5 text-neutral-300" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">
                Live Issue Scraper & 7-Point Detection Engine
              </h3>
              <p className="text-xs text-neutral-400">
                Paste any GitHub issue URL or reference to scrape live issues, detect assignees, OSI licenses, and more.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setShowImportBar(!showImportBar)}
            className="px-3.5 py-1.5 rounded-full text-xs font-semibold bg-white/5 hover:bg-white/10 border border-white/10 text-neutral-300 hover:text-white transition shrink-0 flex items-center gap-1.5 self-start sm:self-auto active:scale-95"
          >
            <span>{showImportBar ? 'Collapse' : 'Expand'}</span>
            {showImportBar ? <ChevronUp className="w-3.5 h-3.5 text-neutral-400" /> : <ChevronDown className="w-3.5 h-3.5 text-neutral-400" />}
          </button>
        </div>

        {/* Expandable Import Form */}
        {showImportBar && (
          <form onSubmit={handleImportSubmit} className="pt-3 border-t border-white/5 space-y-3">
            <div className="flex flex-col sm:flex-row gap-2.5">
              <div className="relative flex-1">
                <Link2 className="w-4 h-4 text-neutral-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={importUrl}
                  onChange={(e) => setImportUrl(e.target.value)}
                  placeholder="Enter GitHub issue URL (e.g. https://github.com/pylint-dev/pylint/issues/11713)"
                  className="w-full bg-[#05080f] border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white/30 font-mono transition"
                />
              </div>
              <button
                type="submit"
                disabled={isImporting}
                className={`px-5 py-2.5 rounded-xl text-xs font-bold flex items-center justify-center gap-2 transition active:scale-95 shrink-0 ${
                  importUrl.trim()
                    ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-md'
                    : 'bg-[#182030] hover:bg-[#1f283c] text-neutral-400 border border-white/10'
                }`}
              >
                {isImporting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Verifying...</span>
                  </>
                ) : (
                  <>
                    <span>Verify & Import</span>
                    <ArrowRight className="w-3.5 h-3.5" />
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

                  <div className="bg-[#05080f] px-2.5 py-1.5 rounded-lg border border-white/10 flex items-center justify-between">
                    <span className="text-neutral-400">License:</span>
                    <span className="text-white font-medium">
                      {importSuccessResult.conditions_checked.license_spdx || 'OSI Verified ✓'}
                    </span>
                  </div>

                  <div className="bg-[#05080f] px-2.5 py-1.5 rounded-lg border border-white/10 flex items-center justify-between">
                    <span className="text-neutral-400">Toolbox Match:</span>
                    <span className="text-white font-medium">
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
      <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-4 sm:p-5 shadow-xl space-y-3.5">
        <form onSubmit={handleSearchSubmit} className="space-y-3.5">
          <div className="flex flex-col sm:flex-row gap-2.5">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-neutral-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search issues by keyword, title, repository..."
                className="w-full bg-[#05080f] border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white/30 transition"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-white font-medium text-xs transition shadow-sm active:scale-95 flex items-center justify-center gap-2 shrink-0"
            >
              <Filter className="w-3.5 h-3.5 text-neutral-400" />
              <span>Apply Filters</span>
            </button>
          </div>

          {/* Filter Dropdowns */}
          <div className="flex flex-wrap items-center gap-2.5 text-xs">
            <div className="relative">
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
                    unassigned_only: unassignedOnly,
                  });
                }}
                className="appearance-none bg-[#05080f] border border-white/10 rounded-xl pl-3 pr-8 py-2 text-xs text-neutral-300 focus:outline-none focus:border-white/30 cursor-pointer"
              >
                <option value="">All Languages</option>
                <option value="Python">Python</option>
                <option value="TypeScript">TypeScript</option>
                <option value="JavaScript">JavaScript</option>
                <option value="Go">Go</option>
                <option value="Rust">Rust</option>
              </select>
              <ChevronDown className="w-3.5 h-3.5 text-neutral-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>

            <div className="relative">
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
                    unassigned_only: unassignedOnly,
                  });
                }}
                className="appearance-none bg-[#05080f] border border-white/10 rounded-xl pl-3 pr-8 py-2 text-xs text-neutral-300 focus:outline-none focus:border-white/30 cursor-pointer"
              >
                <option value="">All Difficulties</option>
                <option value="beginner">Beginner Friendly</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </select>
              <ChevronDown className="w-3.5 h-3.5 text-neutral-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>

            <div className="relative">
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
                    unassigned_only: unassignedOnly,
                  });
                }}
                className="appearance-none bg-[#05080f] border border-white/10 rounded-xl pl-3 pr-8 py-2 text-xs text-neutral-300 focus:outline-none focus:border-white/30 cursor-pointer"
              >
                <option value="">All Licenses</option>
                <option value="VERIFIED_OSI">Verified OSI</option>
                <option value="UNKNOWN">Needs Review / Unknown</option>
                <option value="NO_LICENSE">No License Detected</option>
              </select>
              <ChevronDown className="w-3.5 h-3.5 text-neutral-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
          </div>

          {/* Org Pills with horizontal scrollbar */}
          <div className="overflow-x-auto pb-2 pt-1 [&::-webkit-scrollbar]:h-1.5 [&::-webkit-scrollbar-track]:bg-white/5 [&::-webkit-scrollbar-thumb]:bg-white/20 [&::-webkit-scrollbar-thumb]:rounded-full">
            <div className="flex items-center gap-2 min-w-max">
              <button
                type="button"
                onClick={() => {
                  setSelectedGsocOrg('');
                  onFilterChange({
                    query: searchTerm,
                    language: selectedLanguage,
                    difficulty: selectedDifficulty,
                    license_status: selectedLicense,
                    sort_by: sortBy,
                    gsoc_org: '',
                    unassigned_only: unassignedOnly,
                  });
                }}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 shrink-0 ${
                  selectedGsocOrg === ''
                    ? 'bg-blue-600 text-white font-bold shadow-md shadow-blue-600/20'
                    : 'bg-[#05080f] border border-white/10 text-neutral-400 hover:text-white'
                }`}
              >
                <Building2 className="w-3.5 h-3.5" />
                <span>All Orgs (25)</span>
              </button>

              {trackedOrgs.map((org) => {
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
                        unassigned_only: unassignedOnly,
                      });
                    }}
                    className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 shrink-0 ${
                      isSelected
                        ? 'bg-blue-600 text-white font-bold shadow-md shadow-blue-600/20'
                        : 'bg-[#05080f] border border-white/10 text-neutral-400 hover:text-white'
                    }`}
                  >
                    <span>{org.icon}</span>
                    <span>{org.label}</span>
                    {org.issue_count > 0 && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full font-mono bg-white/10 text-neutral-300 ml-0.5">
                        {org.issue_count}
                      </span>
                    )}
                  </button>
                );
              })}

              <button
                type="button"
                onClick={() => setIsAddOrgModalOpen(true)}
                className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-white/5 hover:bg-white/10 border border-white/10 text-neutral-300 hover:text-white flex items-center gap-1.5 shrink-0 transition"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Org</span>
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Row Above Issues List: All Open Issues, Unassigned Only, Sort */}
      <div className="flex items-center justify-between flex-wrap gap-3 pt-1">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <select className="appearance-none bg-[#0c101a] border border-white/10 rounded-xl pl-3 pr-8 py-1.5 text-xs text-neutral-300 focus:outline-none cursor-pointer">
              <option value="all">All Open Issues</option>
              <option value="assigned">Assigned Issues</option>
            </select>
            <ChevronDown className="w-3 h-3 text-neutral-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          <button
            type="button"
            onClick={() => {
              const next = !unassignedOnly;
              setUnassignedOnly(next);
              onFilterChange({
                query: searchTerm,
                language: selectedLanguage,
                difficulty: selectedDifficulty,
                license_status: selectedLicense,
                sort_by: sortBy,
                gsoc_org: selectedGsocOrg,
                unassigned_only: next,
              });
            }}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-2 border transition ${
              unassignedOnly
                ? 'bg-amber-400/10 text-amber-300 border-amber-400/30 font-bold'
                : 'bg-[#0c101a] border-white/10 text-neutral-300 hover:text-white'
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />
            <span>Unassigned Only</span>
          </button>
        </div>

        <div className="flex items-center gap-2 text-xs text-neutral-400">
          <ArrowUpDown className="w-3.5 h-3.5 text-neutral-400" />
          <span>Sort:</span>
          <div className="relative">
            <select
              value={sortBy}
              onChange={(e) => handleSortChange(e.target.value)}
              className="appearance-none bg-[#0c101a] border border-white/10 rounded-xl pl-2.5 pr-7 py-1 text-xs text-neutral-200 focus:outline-none cursor-pointer"
            >
              <option value="created">Newest</option>
              <option value="rank">Suitability</option>
              <option value="stars">Stars</option>
            </select>
            <ChevronDown className="w-3 h-3 text-neutral-500 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
          <span className="text-neutral-600">|</span>
          <button
            type="button"
            onClick={() => handleSortChange('rank')}
            className={`hover:text-white transition ${sortBy === 'rank' ? 'text-white font-bold' : ''}`}
          >
            Suitability
          </button>
          <span className="text-neutral-600">|</span>
          <button
            type="button"
            onClick={() => handleSortChange('stars')}
            className={`hover:text-white transition ${sortBy === 'stars' ? 'text-white font-bold' : ''}`}
          >
            Stars
          </button>
        </div>
      </div>

      {/* Notification Toast if Cron / Reconcile Feedback active */}
      {gsocSyncFeedback && (
        <div className="bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 px-4 py-2.5 rounded-xl text-xs flex items-center justify-between">
          <span>{gsocSyncFeedback}</span>
          <button onClick={() => setGsocSyncFeedback(null)} className="text-neutral-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
      {reconcileFeedback && (
        <div className="bg-neutral-900 border border-white/15 text-neutral-200 px-4 py-2.5 rounded-xl text-xs flex items-center justify-between">
          <span>{reconcileFeedback}</span>
          <button onClick={() => setReconcileFeedback(null)} className="text-neutral-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 space-y-3">
          <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm">Fetching and evaluating open-source opportunities...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && visibleIssues.length === 0 && (
        <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-8 sm:p-12 text-center space-y-4 shadow-xl">
          <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mx-auto text-white">
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
        {visibleIssues.map((issue) => {
          const breakdown = issue.ranking_breakdown;
          const isTaskActive = Boolean(issue.active_task);

          return (
            <div
              key={issue.id}
              className="p-5 rounded-2xl bg-[#0c101a] hover:bg-[#0e1320] border border-white/10 hover:border-white/20 shadow-xl transition space-y-3.5"
            >
              {/* Top Badges & Suitability Gauge */}
              <div className="flex items-start justify-between gap-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-semibold px-2.5 py-1 rounded-xl bg-white/5 border border-white/10 text-white">
                    {issue.repository?.full_name || issue.repository?.name || 'public/repo'}
                  </span>

                  {issue.repository?.primary_language && (
                    <span className="text-xs font-medium px-2.5 py-1 rounded-xl bg-white/5 border border-white/10 text-neutral-300 flex items-center gap-1.5">
                      <span>🐍</span>
                      <span>{issue.repository.primary_language}</span>
                    </span>
                  )}

                  <div className="flex items-center gap-1 text-xs text-neutral-300 px-2.5 py-1 rounded-xl bg-white/5 border border-white/10">
                    <Star className="w-3 h-3 text-amber-400" />
                    <span>{issue.repository?.stars_count?.toLocaleString() || '12,979'}</span>
                  </div>

                  {/* License or Policy Check */}
                  {issue.policy_status === 'policy_check_required' ? (
                    <span className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-xl bg-amber-950/40 text-amber-400 border border-amber-500/30">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                      <span>Policy Check Required</span>
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-xl bg-white/5 text-neutral-300 border border-white/10">
                      <span className="w-2 h-2 rounded-full border border-neutral-400" />
                      <span>{issue.repository?.license_spdx || 'MIT'}</span>
                    </span>
                  )}
                </div>

                {/* Suitability Score Gauge */}
                <div className="text-right shrink-0">
                  <div className="text-[11px] text-neutral-400 flex items-center justify-end gap-1">
                    <Sparkles className="w-3 h-3 text-cyan-400" />
                    <span>Suitability</span>
                  </div>
                  <div className="text-2xl font-black text-white font-mono tracking-tight mt-0.5">
                    {issue.ranking_score?.toFixed(0) || 65} <span className="text-xs text-neutral-500 font-normal">/100</span>
                  </div>
                </div>
              </div>

              {/* Title and Link */}
              <div>
                <h2 className="text-base font-bold text-white group-hover:text-blue-400 transition flex items-center gap-2">
                  <a
                    href={issue.html_url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-blue-400 transition inline-flex items-center gap-1.5"
                  >
                    <span>#{issue.issue_number} — {issue.title}</span>
                    <ExternalLink className="w-3.5 h-3.5 text-neutral-400" />
                  </a>
                </h2>
              </div>

              {/* Description Excerpt */}
              <p className="text-xs text-neutral-400 line-clamp-2 leading-relaxed">
                {issue.ai_summary || issue.body?.slice(0, 240)}
              </p>

              {/* Bottom Tags & Action Buttons */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-white/5">
                <div className="flex flex-wrap items-center gap-2">
                  {getDifficultyBadge(issue.difficulty_estimate)}
                  <span className="flex items-center gap-1 text-xs text-neutral-400 px-2.5 py-1 rounded-xl bg-white/5 border border-white/10">
                    <Clock className="w-3 h-3 text-neutral-400" />
                    <span>~{issue.estimated_effort_hours || 5}h effort</span>
                  </span>

                  {issue.labels?.slice(0, 3).map((lbl: any, idx: number) => {
                    const name = typeof lbl === 'object' ? lbl.name : lbl;
                    return (
                      <span key={idx} className="text-xs text-neutral-400 px-2.5 py-1 rounded-xl bg-white/5 border border-white/10">
                        {name}
                      </span>
                    );
                  })}
                </div>

                {/* Right Action Buttons */}
                <div className="flex items-center gap-2 self-end sm:self-auto">
                  {onCompleteIssue && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleComplete(issue.id);
                      }}
                      disabled={completingIds.has(issue.id)}
                      title="Mark as completed & remove from inbox"
                      className="px-3.5 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-neutral-300 hover:text-white border border-white/10 text-xs font-semibold transition-all flex items-center gap-1.5 active:scale-95 disabled:opacity-50"
                    >
                      <Check className="w-3.5 h-3.5 stroke-[2.5] text-emerald-400" />
                      <span>Done</span>
                    </button>
                  )}

                  <button
                    onClick={() => onOpenDetails(issue)}
                    className="px-3 py-1.5 text-neutral-300 hover:text-white text-xs font-semibold transition"
                  >
                    Details & Rationale
                  </button>

                  <button
                    onClick={() => onSelectIssue(issue.id)}
                    className="px-4 py-2 rounded-xl bg-white hover:bg-neutral-200 text-black text-xs font-bold shadow-md active:scale-95 transition flex items-center gap-1.5"
                  >
                    <span>{isTaskActive ? 'Resume Task' : 'Select Issue'}</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
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

      {/* Infinite auto-load sentinel & loading indicator right beneath cards grid */}
      <div ref={sentinelRef} className="w-full py-2 flex flex-col items-center justify-center min-h-[48px] pointer-events-none">
        {loadingMore && (
          <div className="flex items-center gap-2.5 px-5 py-2.5 rounded-2xl bg-slate-900 text-white dark:bg-neutral-900 dark:text-white border border-slate-700 dark:border-white/20 shadow-2xl text-xs font-semibold animate-pulse my-2 pointer-events-auto">
            <Loader2 className="w-4 h-4 animate-spin text-indigo-400 dark:text-cyan-400" />
            <span>Auto-loading next batch of issues...</span>
          </div>
        )}
      </div>

      {/* Load More & Infinite Scroll Section */}
      {!loading && visibleIssues.length > 0 && (
        <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/10">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white">Issues Explorer Progress</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-white border border-white/10 font-mono">
                  {visibleIssues.length} / {totalIssues.toLocaleString()} Loaded ({progressPercent}%)
                </span>
              </div>
              <p className="text-[11px] text-neutral-400 mt-0.5">
                {hasMore 
                  ? `${(totalIssues - visibleIssues.length).toLocaleString()} more public issues match your criteria` 
                  : 'All available matching issues have been loaded'}
              </p>
            </div>

            <div className="flex items-center gap-3 text-xs">
              {/* Batch Size Selector */}
              <div className="flex items-center gap-1.5 bg-[#05080f] border border-white/10 rounded-xl px-2.5 py-1">
                <span className="text-neutral-400 text-[11px]">Batch:</span>
                {[25, 50, 100].map(size => (
                  <button
                    key={size}
                    type="button"
                    onClick={() => onPageSizeChange && onPageSizeChange(size)}
                    className={`px-2 py-0.5 rounded-lg text-xs font-medium transition ${
                      pageSize === size
                        ? 'bg-white text-black font-bold shadow-sm'
                        : 'text-neutral-400 hover:text-white'
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
                    ? 'bg-blue-600/20 text-blue-300 border-blue-500/30'
                    : 'bg-[#05080f] text-neutral-400 border-white/10 hover:text-white'
                }`}
                title="Automatically fetch next batch when scrolling near the bottom"
              >
                <span className={`w-2 h-2 rounded-full ${autoLoad ? 'bg-blue-400 animate-pulse' : 'bg-neutral-600'}`} />
                <span>Auto-load: {autoLoad ? 'ON' : 'OFF'}</span>
              </button>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="w-full bg-neutral-900 rounded-full h-2 overflow-hidden border border-white/15">
            <div 
              className="bg-white h-full transition-all duration-300 rounded-full shadow-[0_0_8px_rgba(255,255,255,0.7)]"
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
                className="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-white hover:bg-neutral-200 text-black font-extrabold text-xs shadow-xl active:scale-95 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {loadingMore ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin text-black" />
                    <span className="text-black">Loading next batch of issues...</span>
                  </>
                ) : (
                  <>
                    <Plus className="w-4 h-4 text-black" />
                    <span className="text-black">Load More Issues (+{pageSize || 25})</span>
                    <span className="text-[11px] text-neutral-700 font-semibold">
                      ({(totalIssues - visibleIssues.length).toLocaleString()} remaining)
                    </span>
                  </>
                )}
              </button>
            ) : (
              <div className="py-2 text-center text-xs text-neutral-300 flex items-center justify-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>All {totalIssues.toLocaleString()} {unassignedOnly ? 'open unassigned' : 'open'} issues loaded cleanly.</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add Organization by GitHub Issue Tab URL Modal */}
      {isAddOrgModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-fade-in">
          <div className="liquid-glass-card w-full max-w-lg p-6 rounded-3xl border border-white/20 shadow-2xl space-y-5 animate-scale-up text-slate-900 dark:text-white">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-white/10">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-2xl bg-indigo-500/20 text-indigo-500 flex items-center justify-center">
                  <Building2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold">Add Organization from GitHub</h3>
                  <p className="text-xs text-slate-500 dark:text-neutral-400">
                    Paste the issue tab URL of any open-source or team project
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsAddOrgModalOpen(false);
                  setAddOrgError(null);
                  setAddOrgSuccess(null);
                }}
                className="p-1 rounded-xl text-slate-400 hover:text-slate-900 dark:hover:text-white transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {addOrgSuccess && (
              <div className="p-3.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{addOrgSuccess}</span>
              </div>
            )}

            {addOrgError && (
              <div className="p-3.5 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{addOrgError}</span>
              </div>
            )}

            <form onSubmit={handleAddOrgSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-700 dark:text-neutral-300">
                  GitHub Issue Tab URL
                </label>
                <div className="relative">
                  <Globe className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={addOrgUrl}
                    onChange={(e) => setAddOrgUrl(e.target.value)}
                    placeholder="https://github.com/facebook/react/issues"
                    required
                    autoFocus
                    className="w-full pl-10 pr-3.5 py-2.5 rounded-xl bg-slate-50 dark:bg-[#030303] border border-slate-300 dark:border-white/20 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-neutral-500 text-xs font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <p className="text-[11px] text-slate-500 dark:text-neutral-400">
                  Accepts issue tab URLs, repository links (e.g. <code className="font-mono">facebook/react</code>), or organization pages.
                </p>
              </div>

              {/* Quick suggestions chips */}
              <div className="space-y-1.5">
                <span className="text-[11px] font-medium text-slate-500 dark:text-neutral-400">Popular Quick Presets:</span>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    'facebook/react/issues',
                    'pallets/flask/issues',
                    'astral-sh/uv/issues',
                    'fastapi/fastapi/issues',
                    'tailwindlabs/tailwindcss/issues'
                  ].map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => setAddOrgUrl(`https://github.com/${preset}`)}
                      className="text-[10px] px-2 py-1 rounded-lg bg-slate-100 dark:bg-neutral-800 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 text-slate-700 dark:text-neutral-300 border border-slate-200 dark:border-white/10 transition font-mono"
                    >
                      +{preset}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-700 dark:text-neutral-300">
                  Custom Display Name <span className="text-slate-400 font-normal">(Optional)</span>
                </label>
                <input
                  type="text"
                  value={addOrgName}
                  onChange={(e) => setAddOrgName(e.target.value)}
                  placeholder="e.g., React Core, Flask, FastAPI"
                  className="w-full px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-[#030303] border border-slate-300 dark:border-white/20 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-neutral-500 text-xs focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end gap-2.5 pt-2">
                <button
                  type="button"
                  onClick={() => setIsAddOrgModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-neutral-400 hover:text-slate-900 dark:hover:text-white transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isAddingOrg || !addOrgUrl.trim()}
                  className="px-5 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg transition active:scale-95 disabled:opacity-50 flex items-center gap-2"
                >
                  {isAddingOrg ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Importing Issues...</span>
                    </>
                  ) : (
                    <>
                      <Plus className="w-3.5 h-3.5 stroke-[2.5]" />
                      <span>Add & Sync Issues</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Floating Back-to-Top Button */}
      {showBackToTop && (
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="fixed bottom-6 right-6 z-50 px-4 py-2 rounded-full bg-white hover:bg-neutral-200 text-black shadow-2xl text-xs font-bold transition-all flex items-center gap-1.5 active:scale-95 group cursor-pointer"
          title="Scroll back to top"
        >
          <ArrowUp className="w-3.5 h-3.5 text-black group-hover:-translate-y-0.5 transition-transform shrink-0" />
          <span>Back to Top</span>
        </button>
      )}
    </div>
  );
};
