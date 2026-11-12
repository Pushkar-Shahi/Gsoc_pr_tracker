import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck,
  Users,
  IndianRupee,
  RefreshCw,
  Search,
  Sparkles,
  CheckCircle2,
  XCircle,
  Ban,
  UserCheck,
  Crown,
  RotateCcw,
  Globe,
  Trash2,
  Sliders,
  Activity,
  GitPullRequest,
  AlertTriangle,
  Clock,
  ExternalLink,
  Lock,
  Pencil,
} from 'lucide-react';
import * as api from '../api';
import {
  AdminAuditRecord,
  AdminOverview,
  AdminTaskRecord,
  AdminUserRecord,
  SubscriptionInfo,
  UpiPaymentRequest,
} from '../types';

interface AdminConsoleViewProps {
  subscriptionInfo?: SubscriptionInfo | null;
  onSubscriptionUpdated?: (tier: string) => void;
}

type AdminSubTab = 'overview' | 'users' | 'upi' | 'tasks_audit';

export const AdminConsoleView: React.FC<AdminConsoleViewProps> = ({
  subscriptionInfo,
  onSubscriptionUpdated,
}) => {
  const [subTab, setSubTab] = useState<AdminSubTab>('overview');
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUserRecord[]>([]);
  const [upiRequests, setUpiRequests] = useState<UpiPaymentRequest[]>([]);
  const [tasks, setTasks] = useState<AdminTaskRecord[]>([]);
  const [auditLogs, setAuditLogs] = useState<AdminAuditRecord[]>([]);

  const [userSearch, setUserSearch] = useState('');
  const [upiFilter, setUpiFilter] = useState<'pending' | 'approved' | 'rejected' | 'all'>('pending');
  const [taskSearch, setTaskSearch] = useState('');
  const [taskStateFilter, setTaskStateFilter] = useState('');
  const [auditSearch, setAuditSearch] = useState('');
  const [adminNotes, setAdminNotes] = useState<Record<string, string>>({});

  // Runtime config form state (locked by default to prevent accidental edits)
  const [isEditingConfig, setIsEditingConfig] = useState(false);
  const [cfgBetaMode, setCfgBetaMode] = useState(false);
  const [cfgTrialDays, setCfgTrialDays] = useState(15);
  const [cfgCreditLimit, setCfgCreditLimit] = useState(5);
  const [cfgUpiVpa, setCfgUpiVpa] = useState('8116710520@sbi');

  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const syncRuntimeForm = (ov: AdminOverview) => {
    setCfgBetaMode(Boolean(ov.runtime.free_beta_mode));
    setCfgTrialDays(Number(ov.runtime.free_trial_days ?? 15));
    setCfgCreditLimit(Number(ov.runtime.free_tier_credit_limit ?? 5));
    setCfgUpiVpa(ov.runtime.upi_vpa || '8116710520@sbi');
  };

  const refreshAll = useCallback(async () => {
    setBusyKey('refresh_all');
    try {
      const [ov, usr, upi, tsk, aud] = await Promise.all([
        api.fetchAdminOverview(),
        api.fetchAdminUsers(userSearch),
        api.fetchAdminUpiRequests(upiFilter),
        api.fetchAdminTasks({ state: taskStateFilter || undefined, q: taskSearch || undefined }),
        api.fetchAdminAuditLogs({ q: auditSearch || undefined }),
      ]);
      setOverview(ov);
      syncRuntimeForm(ov);
      setUsers(usr);
      setUpiRequests(upi);
      setTasks(tsk);
      setAuditLogs(aud);
    } catch (err: any) {
      setBanner({ type: 'error', text: err.message || 'Failed to load admin console telemetry' });
    } finally {
      setBusyKey(null);
    }
  }, [userSearch, upiFilter, taskStateFilter, taskSearch, auditSearch]);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.fetchAdminOverview(),
      api.fetchAdminUsers(),
      api.fetchAdminUpiRequests('pending'),
      api.fetchAdminTasks(),
      api.fetchAdminAuditLogs(),
    ])
      .then(([ov, usr, upi, tsk, aud]) => {
        if (!active) return;
        setOverview(ov);
        syncRuntimeForm(ov);
        setUsers(usr);
        setUpiRequests(upi);
        setTasks(tsk);
        setAuditLogs(aud);
      })
      .catch((err: any) => {
        if (active) {
          setBanner({ type: 'error', text: err.message || 'Failed to load admin data' });
        }
      });
    return () => {
      active = false;
    };
  }, []);

  if (!subscriptionInfo?.is_admin) {
    return (
      <div className="max-w-2xl mx-auto mt-10 p-8 rounded-2xl border border-rose-200 bg-rose-50/70 dark:border-rose-500/30 dark:bg-rose-950/20 text-center space-y-2">
        <ShieldCheck className="w-8 h-8 text-rose-500 mx-auto" />
        <h2 className="text-base font-bold text-slate-900 dark:text-white">Platform Admin Access Required</h2>
        <p className="text-xs text-slate-600 dark:text-neutral-300">
          This control center is restricted to platform superusers.
        </p>
      </div>
    );
  }

  const runAction = async (key: string, fn: () => Promise<string | void>, syncSub = false) => {
    setBusyKey(key);
    setBanner(null);
    try {
      const msg = await fn();
      await refreshAll();
      if (syncSub) {
        const latestSub = await api.fetchSubscriptionInfo().catch(() => null);
        if (latestSub && onSubscriptionUpdated) {
          onSubscriptionUpdated(latestSub.tier);
        }
      }
      if (msg) setBanner({ type: 'success', text: msg });
    } catch (err: any) {
      setBanner({ type: 'error', text: err.message || 'Admin operation failed' });
    } finally {
      setBusyKey(null);
    }
  };

  const handleSaveRuntimeConfig = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isEditingConfig) return;
    runAction(
      'save_runtime',
      async () => {
        const res = await api.updateAdminRuntimeConfig({
          free_beta_mode: cfgBetaMode,
          free_trial_days: cfgTrialDays,
          free_tier_credit_limit: cfgCreditLimit,
          upi_vpa: cfgUpiVpa,
        });
        setIsEditingConfig(false);
        return `Saved live settings: Trial=${res.runtime.free_trial_days}d, Credits=${res.runtime.free_tier_credit_limit}, VPA=${res.runtime.upi_vpa}, FreeBeta=${res.runtime.free_beta_mode ? 'ON' : 'OFF'}`;
      },
      true
    );
  };

  const handleCancelConfigEdit = () => {
    if (overview) {
      syncRuntimeForm(overview);
    }
    setIsEditingConfig(false);
  };

  const runtimeInputClass = isEditingConfig
    ? 'w-full px-3 py-2 rounded-xl border border-indigo-400 dark:border-indigo-500/60 bg-white dark:bg-black/40 text-slate-900 dark:text-white font-mono text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/30 transition'
    : 'w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-white/5 bg-slate-200/70 dark:bg-white/[0.04] text-slate-500 dark:text-neutral-400 font-mono text-xs cursor-not-allowed select-none opacity-80 transition';

  const subTabs: Array<{ id: AdminSubTab; label: string; icon: React.ComponentType<{ className?: string }>; badge?: number }> = [
    { id: 'overview', label: 'Overview & Controls', icon: Sliders },
    { id: 'users', label: 'Users & Plans', icon: Users, badge: overview?.users.total },
    { id: 'upi', label: 'UPI Queue', icon: IndianRupee, badge: overview?.upi.pending_count },
    { id: 'tasks_audit', label: 'Tasks & Audit', icon: Activity },
  ];

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-16 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200 dark:border-white/10">
        <div className="flex items-start gap-3">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-purple-600 via-indigo-600 to-blue-600 text-white flex items-center justify-center shadow-lg shadow-indigo-500/20 shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
                Platform Admin Console
              </h1>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 border border-purple-200 dark:bg-purple-500/20 dark:text-purple-200 dark:border-purple-500/30">
                GOD MODE
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-neutral-400 mt-0.5">
              Manage users, grant Pro/Team/trials, reset Starter credits, review UPI UTRs, inspect tasks & update live config without touching the backend.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => refreshAll()}
          disabled={busyKey === 'refresh_all'}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 hover:bg-slate-50 dark:hover:bg-white/10 text-xs font-semibold text-slate-700 dark:text-neutral-200 transition self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${busyKey === 'refresh_all' ? 'animate-spin' : ''}`} />
          <span>Sync Live Telemetry</span>
        </button>
      </div>

      {/* Status Banner */}
      {banner && (
        <div
          className={`p-3.5 rounded-xl border text-xs font-medium flex items-center justify-between gap-3 ${
            banner.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-500/10 dark:border-emerald-500/30 dark:text-emerald-200'
              : 'bg-rose-50 border-rose-200 text-rose-800 dark:bg-rose-500/10 dark:border-rose-500/30 dark:text-rose-200'
          }`}
        >
          <div className="flex items-center gap-2">
            {banner.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertTriangle className="w-4 h-4 shrink-0" />}
            <span>{banner.text}</span>
          </div>
          <button type="button" onClick={() => setBanner(null)} className="opacity-70 hover:opacity-100 font-bold">
            ✕
          </button>
        </div>
      )}

      {/* Navigation Pills */}
      <div className="flex flex-wrap items-center gap-2">
        {subTabs.map((t) => {
          const Icon = t.icon;
          const active = subTab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setSubTab(t.id)}
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold border transition ${
                active
                  ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm shadow-indigo-500/25'
                  : 'bg-white dark:bg-[#0d121c] text-slate-600 dark:text-neutral-300 border-slate-200 dark:border-white/10 hover:bg-slate-50 dark:hover:bg-white/5'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{t.label}</span>
              {typeof t.badge === 'number' && t.badge > 0 && (
                <span
                  className={`px-1.5 py-0.5 rounded-full text-[10px] font-mono font-bold ${
                    active
                      ? 'bg-white/20 text-white'
                      : t.id === 'upi'
                      ? 'bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300'
                      : 'bg-slate-100 text-slate-700 dark:bg-white/10 dark:text-neutral-300'
                  }`}
                >
                  {t.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* TAB 1: OVERVIEW & LIVE CONTROLS */}
      {subTab === 'overview' && overview && (
        <div className="space-y-6">
          {/* KPI Grid */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3.5">
            <div className="p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0d121c] space-y-1">
              <div className="text-[11px] font-semibold text-slate-500 dark:text-neutral-400">Users</div>
              <div className="text-2xl font-bold text-slate-900 dark:text-white font-mono">{overview.users.total}</div>
              <div className="text-[10px] text-slate-500 dark:text-neutral-400">
                {overview.users.active} active • {overview.users.superusers} admins • {overview.users.suspended} suspended
              </div>
            </div>

            <div className="p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0d121c] space-y-1">
              <div className="text-[11px] font-semibold text-slate-500 dark:text-neutral-400">Workspaces & Trials</div>
              <div className="text-2xl font-bold text-slate-900 dark:text-white font-mono">{overview.organizations.total}</div>
              <div className="text-[10px] text-slate-500 dark:text-neutral-400">
                Pro: {overview.organizations.by_tier.pro || 0} ({overview.organizations.active_trials} trial) • Starter: {overview.organizations.by_tier.starter || 0}
              </div>
            </div>

            <div className="p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0d121c] space-y-1">
              <div className="text-[11px] font-semibold text-slate-500 dark:text-neutral-400">GSoC Issues Pool</div>
              <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 font-mono">
                {overview.issues.eligible_open}
              </div>
              <div className="text-[10px] text-slate-500 dark:text-neutral-400">
                {overview.issues.total} total • {overview.issues.repositories} repos
              </div>
            </div>

            <div className="p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0d121c] space-y-1">
              <div className="text-[11px] font-semibold text-slate-500 dark:text-neutral-400">Tasks & PRs</div>
              <div className="text-2xl font-bold text-blue-600 dark:text-blue-400 font-mono">{overview.tasks.total}</div>
              <div className="text-[10px] text-slate-500 dark:text-neutral-400">
                {overview.tasks.pr_created} PRs • {overview.tasks.merged} merged • {overview.tasks.blocked} blocked
              </div>
            </div>

            <div className="p-4 rounded-2xl border border-amber-200 dark:border-amber-500/30 bg-gradient-to-br from-amber-50/80 to-rose-50/50 dark:from-amber-950/30 dark:to-rose-950/20 space-y-1 col-span-2 lg:col-span-1">
              <div className="text-[11px] font-semibold text-amber-800 dark:text-amber-200">UPI Approved Revenue</div>
              <div className="text-2xl font-bold text-amber-900 dark:text-amber-300 font-mono">
                ₹{overview.upi.total_revenue_inr}
              </div>
              <div className="text-[10px] text-amber-700/90 dark:text-amber-200/80">
                Plans: ₹{overview.upi.plan_revenue_inr} • Tips: ₹{overview.upi.support_tips_inr} • {overview.upi.pending_count} pending
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Global Worker & Discovery Controls */}
            <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0d121c] space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Globe className="w-4 h-4 text-blue-500" />
                  <h2 className="text-sm font-bold text-slate-900 dark:text-white">Global Discovery & Database Maintenance</h2>
                </div>
                <span
                  className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${
                    overview.issues.worker_running
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300'
                      : 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300'
                  }`}
                >
                  {overview.issues.worker_running ? 'CRON ACTIVE' : 'CRON IDLE'}
                </span>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-200 dark:border-white/5 text-xs text-slate-600 dark:text-neutral-300 space-y-1">
                <div>
                  Last Scan:{' '}
                  <span className="font-mono text-slate-900 dark:text-white">
                    {overview.issues.last_scan_at ? new Date(overview.issues.last_scan_at).toLocaleString() : 'Never'}
                  </span>
                </div>
                <div>
                  GitHub Token:{' '}
                  <span className="font-mono font-semibold">
                    {overview.runtime.github_token_configured ? 'Configured' : 'Unauthenticated (60 req/hr limit)'}
                  </span>
                </div>
                <div>
                  Hybrid Runners Online:{' '}
                  <span className="font-mono font-semibold">
                    {overview.runners.online} / {overview.runners.total} ({overview.runners.active_jobs} queued/running jobs)
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap gap-2.5">
                <button
                  type="button"
                  onClick={() =>
                    runAction('global_scan', async () => {
                      const res = await api.triggerAdminGlobalDiscovery();
                      return `Global 2h scan completed (${res.total_discovered ?? 0} issues synced).`;
                    })
                  }
                  disabled={busyKey === 'global_scan'}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-sm transition disabled:opacity-60"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${busyKey === 'global_scan' ? 'animate-spin' : ''}`} />
                  <span>{busyKey === 'global_scan' ? 'Scanning GitHub...' : 'Run Global 2h Discovery Scan'}</span>
                </button>

                <button
                  type="button"
                  onClick={() =>
                    runAction('reconcile_issues', async () => {
                      const res = await api.triggerAdminIssueReconcile(true);
                      return `Upstream cleanup completed: ${JSON.stringify(res.summary || {})}`;
                    })
                  }
                  disabled={busyKey === 'reconcile_issues'}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-100 hover:bg-slate-200 dark:bg-white/5 dark:hover:bg-white/10 text-slate-800 dark:text-white text-xs font-semibold transition disabled:opacity-60"
                >
                  <Trash2 className="w-3.5 h-3.5 text-amber-500" />
                  <span>{busyKey === 'reconcile_issues' ? 'Purging Closed Issues...' : 'Prune Closed / Assigned Issues'}</span>
                </button>
              </div>
            </div>

            {/* Live Runtime Monetization & UPI Config */}
            <form
              onSubmit={handleSaveRuntimeConfig}
              className={`p-5 rounded-2xl border space-y-4 transition ${
                isEditingConfig
                  ? 'border-indigo-300 dark:border-indigo-500/40 bg-white dark:bg-[#0d121c] shadow-sm shadow-indigo-500/10'
                  : 'border-slate-200 dark:border-white/10 bg-slate-50/80 dark:bg-[#0b0f17]'
              }`}
            >
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <Sparkles className={`w-4 h-4 ${isEditingConfig ? 'text-purple-500' : 'text-slate-400 dark:text-neutral-500'}`} />
                  <h2 className="text-sm font-bold text-slate-900 dark:text-white">Live Monetization & UPI Settings</h2>
                  <span
                    className={`inline-flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${
                      isEditingConfig
                        ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300'
                        : 'bg-slate-200 text-slate-600 dark:bg-white/10 dark:text-neutral-400'
                    }`}
                  >
                    <Lock className="w-2.5 h-2.5" />
                    <span>{isEditingConfig ? 'EDITING UNLOCKED' : 'READ-ONLY'}</span>
                  </span>
                </div>

                {!isEditingConfig ? (
                  <button
                    type="button"
                    onClick={() => setIsEditingConfig(true)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-300 dark:border-white/15 bg-white dark:bg-white/5 hover:bg-slate-100 dark:hover:bg-white/10 text-xs font-semibold text-slate-700 dark:text-neutral-200 transition active:scale-95"
                  >
                    <Pencil className="w-3 h-3" />
                    <span>Edit Settings</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleCancelConfigEdit}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-100 dark:bg-white/5 hover:bg-slate-200 dark:hover:bg-white/10 text-xs font-semibold text-slate-600 dark:text-neutral-300 transition"
                  >
                    <span>Cancel</span>
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="space-y-1 text-xs">
                  <span className={`font-semibold ${isEditingConfig ? 'text-slate-700 dark:text-neutral-300' : 'text-slate-500 dark:text-neutral-400'}`}>
                    Default Pro Trial Length (Days)
                  </span>
                  <input
                    type="number"
                    min={0}
                    max={365}
                    disabled={!isEditingConfig}
                    value={cfgTrialDays}
                    onChange={(e) => setCfgTrialDays(Number(e.target.value))}
                    className={runtimeInputClass}
                  />
                </label>

                <label className="space-y-1 text-xs">
                  <span className={`font-semibold ${isEditingConfig ? 'text-slate-700 dark:text-neutral-300' : 'text-slate-500 dark:text-neutral-400'}`}>
                    Starter One-Time Credit Limit
                  </span>
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    disabled={!isEditingConfig}
                    value={cfgCreditLimit}
                    onChange={(e) => setCfgCreditLimit(Number(e.target.value))}
                    className={runtimeInputClass}
                  />
                </label>

                <label className="space-y-1 text-xs sm:col-span-2">
                  <span className={`font-semibold ${isEditingConfig ? 'text-slate-700 dark:text-neutral-300' : 'text-slate-500 dark:text-neutral-400'}`}>
                    Receiving UPI VPA (Plans & Support QR)
                  </span>
                  <input
                    type="text"
                    disabled={!isEditingConfig}
                    value={cfgUpiVpa}
                    onChange={(e) => setCfgUpiVpa(e.target.value)}
                    placeholder="8116710520@sbi"
                    className={runtimeInputClass}
                  />
                </label>
              </div>

              <label
                className={`flex items-center justify-between p-3 rounded-xl border transition ${
                  isEditingConfig
                    ? 'border-indigo-300/70 dark:border-indigo-500/30 bg-slate-50 dark:bg-white/[0.03] cursor-pointer'
                    : 'border-slate-200 dark:border-white/5 bg-slate-200/60 dark:bg-white/[0.03] cursor-not-allowed opacity-75'
                }`}
              >
                <div>
                  <div className={`text-xs font-bold ${isEditingConfig ? 'text-slate-900 dark:text-white' : 'text-slate-600 dark:text-neutral-300'}`}>
                    Free Beta Mode (Unlock Pro for Everyone)
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-neutral-400">
                    When OFF, new users receive {cfgTrialDays}-day Pro trial then fall back to {cfgCreditLimit} credits on Starter.
                  </div>
                </div>
                <input
                  type="checkbox"
                  disabled={!isEditingConfig}
                  checked={cfgBetaMode}
                  onChange={(e) => setCfgBetaMode(e.target.checked)}
                  className={`w-4 h-4 accent-indigo-600 ${!isEditingConfig ? 'cursor-not-allowed opacity-60' : ''}`}
                />
              </label>

              {isEditingConfig ? (
                <div className="flex items-center gap-2.5">
                  <button
                    type="submit"
                    disabled={busyKey === 'save_runtime'}
                    className="flex-1 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-xs font-bold shadow-sm transition disabled:opacity-60"
                  >
                    {busyKey === 'save_runtime' ? 'Applying Settings...' : 'Save & Apply Live Config'}
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelConfigEdit}
                    className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-100 hover:bg-slate-200 dark:bg-white/5 dark:hover:bg-white/10 text-xs font-semibold text-slate-700 dark:text-neutral-300 transition"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="w-full py-2.5 px-3 rounded-xl bg-slate-200/70 dark:bg-white/[0.04] border border-slate-200 dark:border-white/5 text-center text-[11px] font-medium text-slate-500 dark:text-neutral-400 flex items-center justify-center gap-1.5">
                  <Lock className="w-3 h-3" />
                  <span>Protected against accidental changes — click Edit Settings above to modify.</span>
                </div>
              )}
            </form>
          </div>
        </div>
      )}

      {/* TAB 2: USERS & PLAN OVERRIDES */}
      {subTab === 'users' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-2.5">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    runAction('search_users', async () => {
                      await api.fetchAdminUsers(userSearch).then(setUsers);
                    });
                  }
                }}
                placeholder="Search users by GitHub handle, email, or name..."
                className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0d121c] text-xs text-slate-900 dark:text-white"
              />
            </div>
            <button
              type="button"
              onClick={() =>
                runAction('search_users', async () => {
                  const list = await api.fetchAdminUsers(userSearch);
                  setUsers(list);
                })
              }
              className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold"
            >
              Search Users
            </button>
          </div>

          {users.length === 0 ? (
            <div className="p-8 rounded-2xl border border-dashed border-slate-300 dark:border-white/10 text-center text-xs text-slate-500">
              No matching users found.
            </div>
          ) : (
            <div className="space-y-3">
              {users.map((u) => (
                <div
                  key={u.id}
                  className="p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0d121c] space-y-3"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      {u.avatar_url ? (
                        <img src={u.avatar_url} alt={u.github_username} className="w-9 h-9 rounded-full border border-slate-200 dark:border-white/10" />
                      ) : (
                        <div className="w-9 h-9 rounded-full bg-indigo-500/15 text-indigo-600 dark:text-indigo-300 flex items-center justify-center font-bold text-xs">
                          {(u.github_username || 'U')[0].toUpperCase()}
                        </div>
                      )}
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-bold text-slate-900 dark:text-white">@{u.github_username}</span>
                          {u.is_superuser && (
                            <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 dark:bg-purple-500/20 dark:text-purple-200">
                              ADMIN
                            </span>
                          )}
                          {!u.is_active && (
                            <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300">
                              SUSPENDED
                            </span>
                          )}
                          {u.is_current_admin && (
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-300">
                              YOU
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-500 dark:text-neutral-400">
                          {u.email || 'No email'} • {u.tasks_total} tasks created • Joined{' '}
                          {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                        </div>
                      </div>
                    </div>

                    {!u.is_current_admin && (
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() =>
                            runAction(`admin_toggle_${u.id}`, async () => {
                              await api.updateAdminUserStatus(u.id, { is_superuser: !u.is_superuser });
                              return `${u.is_superuser ? 'Revoked admin from' : 'Promoted'} @${u.github_username}`;
                            })
                          }
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-purple-200 dark:border-purple-500/30 bg-purple-50 dark:bg-purple-500/10 text-purple-700 dark:text-purple-200 text-[11px] font-semibold hover:opacity-90"
                        >
                          <Crown className="w-3 h-3" />
                          <span>{u.is_superuser ? 'Revoke Admin' : 'Make Admin'}</span>
                        </button>

                        <button
                          type="button"
                          onClick={() =>
                            runAction(`active_toggle_${u.id}`, async () => {
                              await api.updateAdminUserStatus(u.id, { is_active: !u.is_active });
                              return `${u.is_active ? 'Suspended' : 'Reactivated'} @${u.github_username}`;
                            })
                          }
                          className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border text-[11px] font-semibold hover:opacity-90 ${
                            u.is_active
                              ? 'border-rose-200 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300'
                              : 'border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                          }`}
                        >
                          {u.is_active ? <Ban className="w-3 h-3" /> : <UserCheck className="w-3 h-3" />}
                          <span>{u.is_active ? 'Suspend' : 'Activate'}</span>
                        </button>
                      </div>
                    )}
                  </div>

                  {/* User's Workspaces & Direct Plan Controls */}
                  {u.workspaces.length > 0 && (
                    <div className="space-y-2 pt-2 border-t border-slate-100 dark:border-white/5">
                      {u.workspaces.map((ws) => (
                        <div
                          key={ws.org_id}
                          className="p-3 rounded-xl bg-slate-50 dark:bg-white/[0.025] border border-slate-200/80 dark:border-white/5 flex flex-col lg:flex-row lg:items-center justify-between gap-2.5"
                        >
                          <div className="space-y-0.5 text-xs">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-bold text-slate-800 dark:text-neutral-100">{ws.org_name}</span>
                              <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 dark:bg-blue-500/20 dark:text-blue-200 font-bold">
                                {ws.billing_tier}
                              </span>
                              {ws.trial_active && (
                                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300 font-semibold">
                                  Trial: {ws.trial_days_remaining}d left
                                </span>
                              )}
                              {ws.trial_expired && (
                                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300 font-semibold">
                                  Trial Ended
                                </span>
                              )}
                            </div>
                            <div className="text-[11px] text-slate-500 dark:text-neutral-400 font-mono">
                              Credits Used: {ws.tasks_used}
                              {ws.task_limit !== null ? ` / ${ws.task_limit}` : ' (Unlimited)'} • Org ID: {ws.org_id.slice(0, 14)}…
                            </div>
                          </div>

                          <div className="flex flex-wrap items-center gap-1.5">
                            {(['pro', 'team', 'starter'] as const).map((tier) => (
                              <button
                                key={tier}
                                type="button"
                                onClick={() =>
                                  runAction(
                                    `tier_${ws.org_id}_${tier}`,
                                    async () => {
                                      await api.overrideAdminOrgPlan(ws.org_id, { tier });
                                      return `Switched "${ws.org_name}" to ${tier.toUpperCase()}.`;
                                    },
                                    true
                                  )
                                }
                                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition ${
                                  ws.billing_tier === tier && !ws.trial_active
                                    ? 'bg-indigo-600 text-white border-indigo-600'
                                    : 'bg-white dark:bg-white/5 border-slate-200 dark:border-white/10 text-slate-700 dark:text-neutral-200 hover:bg-slate-100 dark:hover:bg-white/10'
                                }`}
                              >
                                {tier === 'pro' ? 'Grant Pro' : tier === 'team' ? 'Grant Team' : 'Set Starter'}
                              </button>
                            ))}

                            <button
                              type="button"
                              onClick={() =>
                                runAction(
                                  `trial15_${ws.org_id}`,
                                  async () => {
                                    await api.overrideAdminOrgPlan(ws.org_id, { tier: 'pro', trial_days: 15 });
                                    return `Granted fresh 15-day Pro Trial to "${ws.org_name}".`;
                                  },
                                  true
                                )
                              }
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-indigo-200 dark:border-indigo-500/30 bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-200 hover:opacity-90"
                            >
                              <Clock className="w-3 h-3" />
                              <span>+15d Trial</span>
                            </button>

                            <button
                              type="button"
                              onClick={() =>
                                runAction(
                                  `reset_${ws.org_id}`,
                                  async () => {
                                    await api.resetAdminOrgCredits(ws.org_id);
                                    return `Reset Starter task credits to 0 for "${ws.org_name}".`;
                                  },
                                  true
                                )
                              }
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-200 hover:opacity-90"
                            >
                              <RotateCcw className="w-3 h-3" />
                              <span>Reset Credits</span>
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: UPI PAYMENT QUEUE */}
      {subTab === 'upi' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-white/5 p-1 rounded-xl">
              {(['pending', 'approved', 'rejected', 'all'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => {
                    setUpiFilter(tab);
                    runAction(`upi_filter_${tab}`, async () => {
                      const list = await api.fetchAdminUpiRequests(tab);
                      setUpiRequests(list);
                    });
                  }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition ${
                    upiFilter === tab
                      ? 'bg-white dark:bg-white/10 text-slate-900 dark:text-white shadow-xs'
                      : 'text-slate-600 dark:text-neutral-400'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
            {overview && (
              <div className="text-xs font-mono font-bold text-amber-700 dark:text-amber-300">
                Total Approved: ₹{overview.upi.total_revenue_inr} (Plans ₹{overview.upi.plan_revenue_inr} • Tips ₹{overview.upi.support_tips_inr})
              </div>
            )}
          </div>

          {upiRequests.length === 0 ? (
            <div className="p-8 rounded-2xl border border-dashed border-slate-300 dark:border-white/10 text-center text-xs text-slate-500">
              No {upiFilter === 'all' ? '' : upiFilter} UPI submissions found.
            </div>
          ) : (
            <div className="space-y-3">
              {upiRequests.map((req) => (
                <div
                  key={req.id}
                  className="p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0d121c] space-y-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono font-bold text-slate-900 dark:text-white text-sm">₹{req.amount_inr}</span>
                      <span className="font-bold text-slate-800 dark:text-neutral-100">
                        {req.payment_purpose === 'support'
                          ? 'Developer Support Tip'
                          : `${(req.plan_tier || 'pro').toUpperCase()} • ${req.billing_cycle}`}
                      </span>
                      <span className="font-mono text-purple-700 dark:text-purple-300 bg-purple-100 dark:bg-purple-500/20 px-2 py-0.5 rounded font-semibold">
                        UTR: {req.utr_number}
                      </span>
                    </div>
                    <span className="text-[11px] font-mono uppercase text-slate-500">{req.status}</span>
                  </div>

                  <div className="text-[11px] text-slate-600 dark:text-neutral-300">
                    Payer: <span className="font-semibold">{req.payer_username || 'User'}</span> ({req.payer_email || 'no email'})
                    {req.payer_upi_id ? ` • Sender UPI: ${req.payer_upi_id}` : ''} • Receiver: {req.upi_vpa}
                    {req.note ? ` • Note: "${req.note}"` : ''}
                  </div>

                  {req.status === 'pending' && (
                    <div className="flex flex-col sm:flex-row gap-2">
                      <input
                        type="text"
                        value={adminNotes[req.id] || ''}
                        onChange={(e) => setAdminNotes((prev) => ({ ...prev, [req.id]: e.target.value }))}
                        placeholder="Optional reviewer note..."
                        className="flex-1 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-black/30 text-xs text-slate-900 dark:text-white"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          runAction(
                            `approve_${req.id}`,
                            async () => {
                              await api.reviewAdminUpiRequest(req.id, 'approve', adminNotes[req.id]);
                              return `Approved ₹${req.amount_inr} payment (UTR ${req.utr_number}).`;
                            },
                            true
                          )
                        }
                        className="inline-flex items-center justify-center gap-1 px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Approve & Activate</span>
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          runAction(`reject_${req.id}`, async () => {
                            await api.reviewAdminUpiRequest(req.id, 'reject', adminNotes[req.id] || 'UTR not matched in SBI statement.');
                            return `Rejected UTR ${req.utr_number}.`;
                          })
                        }
                        className="inline-flex items-center justify-center gap-1 px-3.5 py-1.5 rounded-lg border border-rose-200 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300 text-xs font-bold"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        <span>Reject</span>
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 4: GLOBAL TASKS & AUDIT LOGS */}
      {subTab === 'tasks_audit' && (
        <div className="space-y-6">
          {/* Global Tasks */}
          <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0d121c] space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <GitPullRequest className="w-4 h-4 text-blue-500" />
                <h2 className="text-sm font-bold text-slate-900 dark:text-white">Cross-Tenant Tasks Monitor</h2>
              </div>
              <div className="flex flex-wrap gap-2">
                <input
                  type="text"
                  value={taskSearch}
                  onChange={(e) => setTaskSearch(e.target.value)}
                  placeholder="Filter repo, user, or title..."
                  className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-black/30 text-xs text-slate-900 dark:text-white"
                />
                <select
                  value={taskStateFilter}
                  onChange={(e) => setTaskStateFilter(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-black/30 text-xs text-slate-900 dark:text-white"
                >
                  <option value="">All States</option>
                  <option value="SELECTED">SELECTED</option>
                  <option value="IMPLEMENTATION_IN_PROGRESS">IN PROGRESS</option>
                  <option value="BLOCKED">BLOCKED</option>
                  <option value="PR_CREATED">PR CREATED</option>
                  <option value="MERGED">MERGED</option>
                  <option value="CANCELED">CANCELED</option>
                </select>
                <button
                  type="button"
                  onClick={() =>
                    runAction('filter_tasks', async () => {
                      const list = await api.fetchAdminTasks({ state: taskStateFilter || undefined, q: taskSearch || undefined });
                      setTasks(list);
                    })
                  }
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-semibold"
                >
                  Apply
                </button>
              </div>
            </div>

            {tasks.length === 0 ? (
              <div className="text-xs text-slate-500 text-center py-6">No tasks match the current filter.</div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                {tasks.map((t) => (
                  <div
                    key={t.id}
                    className="p-3 rounded-xl border border-slate-200/80 dark:border-white/5 bg-slate-50 dark:bg-white/[0.02] flex flex-col lg:flex-row lg:items-center justify-between gap-2 text-xs"
                  >
                    <div className="space-y-0.5 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded bg-blue-100 text-blue-800 dark:bg-blue-500/20 dark:text-blue-200">
                          {t.workflow_state}
                        </span>
                        <span className="font-bold text-slate-900 dark:text-white truncate">
                          {t.repo_full_name}#{t.issue_number}
                        </span>
                        <a
                          href={t.pr_url || t.issue_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline truncate"
                        >
                          <span className="truncate max-w-xs">{t.issue_title}</span>
                          <ExternalLink className="w-3 h-3 shrink-0" />
                        </a>
                      </div>
                      <div className="text-[11px] text-slate-500 dark:text-neutral-400">
                        User: @{t.username || 'unknown'} • Workspace: {t.org_name || '—'}
                        {t.blocked_reason ? ` • Blocked: ${t.blocked_reason}` : ''}
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      {t.workflow_state !== 'SELECTED' && (
                        <button
                          type="button"
                          onClick={() =>
                            runAction(`force_sel_${t.id}`, async () => {
                              await api.forceAdminTaskState(t.id, 'SELECTED', '');
                              return `Reset ${t.repo_full_name}#${t.issue_number} to SELECTED.`;
                            })
                          }
                          className="px-2 py-1 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 text-[11px] font-semibold hover:bg-slate-100 dark:hover:bg-white/10"
                        >
                          Reset / Unblock
                        </button>
                      )}
                      {t.workflow_state !== 'CANCELED' && (
                        <button
                          type="button"
                          onClick={() =>
                            runAction(`force_cancel_${t.id}`, async () => {
                              await api.forceAdminTaskState(t.id, 'CANCELED', 'Canceled by platform admin');
                              return `Canceled ${t.repo_full_name}#${t.issue_number}.`;
                            })
                          }
                          className="px-2 py-1 rounded-lg border border-rose-200 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300 text-[11px] font-semibold"
                        >
                          Force Cancel
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Global Audit Stream */}
          <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-[#0d121c] space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-purple-500" />
                <h2 className="text-sm font-bold text-slate-900 dark:text-white">Global Cross-Tenant Audit Log</h2>
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={auditSearch}
                  onChange={(e) => setAuditSearch(e.target.value)}
                  placeholder="Search action, actor, or org..."
                  className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-black/30 text-xs text-slate-900 dark:text-white"
                />
                <button
                  type="button"
                  onClick={() =>
                    runAction('filter_audit', async () => {
                      const list = await api.fetchAdminAuditLogs({ q: auditSearch || undefined });
                      setAuditLogs(list);
                    })
                  }
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-semibold"
                >
                  Filter
                </button>
              </div>
            </div>

            <div className="space-y-1.5 max-h-80 overflow-y-auto pr-1">
              {auditLogs.map((log) => (
                <div
                  key={log.id}
                  className="p-2.5 rounded-lg bg-slate-50 dark:bg-white/[0.02] border border-slate-200/70 dark:border-white/5 text-[11px] flex flex-col sm:flex-row sm:items-center justify-between gap-1"
                >
                  <div className="space-y-0.5 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono font-bold text-indigo-700 dark:text-indigo-300">{log.action}</span>
                      <span className="px-1.5 py-0.2 rounded bg-slate-200 dark:bg-white/10 font-mono text-[10px]">{log.actor}</span>
                      {log.username && <span className="text-slate-700 dark:text-neutral-200">@{log.username}</span>}
                      {log.org_name && <span className="text-slate-500 dark:text-neutral-400">({log.org_name})</span>}
                    </div>
                    {Object.keys(log.details || {}).length > 0 && (
                      <div className="font-mono text-[10px] text-slate-500 dark:text-neutral-400 truncate">
                        {JSON.stringify(log.details)}
                      </div>
                    )}
                  </div>
                  <div className="font-mono text-[10px] text-slate-400 shrink-0">
                    {log.created_at ? new Date(log.created_at).toLocaleString() : ''}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
