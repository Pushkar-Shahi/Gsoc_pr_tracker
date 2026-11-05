import React, { useState, useEffect, useCallback } from 'react';
import { 
  Layers, GitPullRequest, Settings as SettingsIcon, History, 
  ShieldCheck, Search, Cpu, CreditCard, Coins
} from 'lucide-react';

import { Issue, Task, PlatformSettings, DiscoveryStatus, AuditLog, SubscriptionInfo } from './types';
import * as api from './api';

import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { IssueInbox } from './components/IssueInbox';
import { IssueDetailsModal } from './components/IssueDetailsModal';
import { TrackedIssuesView } from './components/TrackedIssuesView';
import { PullRequestsView } from './components/PullRequestsView';
import { ActivityHistoryView } from './components/ActivityHistoryView';
import { RunnersView } from './components/RunnersView';
import { BillingView } from './components/BillingView';
import { UpgradeModal } from './components/UpgradeModal';
import { BountiesView } from './components/BountiesView';
import { SettingsView } from './components/SettingsView';
import { NotificationsPanel } from './components/NotificationsPanel';
import { promptPWAInstall } from './registerSW';

export function App() {
  const [activeTab, setActiveTab] = useState<'issues' | 'bounties' | 'tracker' | 'prs' | 'history' | 'runners' | 'billing' | 'settings'>('issues');
  const [isInstallable, setIsInstallable] = useState(false);
  const [planTier, setPlanTier] = useState<string>('starter');
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [upgradeReason, setUpgradeReason] = useState<string | undefined>(undefined);

  // Tracked Items & PRs
  const [tasks, setTasks] = useState<Task[]>([]);
  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [discoveryStatus, setDiscoveryStatus] = useState<DiscoveryStatus | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);

  // Issue Finder State
  const [issues, setIssues] = useState<Issue[]>([]);
  const [totalIssues, setTotalIssues] = useState(0);
  const [loadingIssues, setLoadingIssues] = useState(false);
  const [loadingMoreIssues, setLoadingMoreIssues] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [selectedIssueModal, setSelectedIssueModal] = useState<Issue | null>(null);
  const [issueFilters, setIssueFilters] = useState<Record<string, any>>({});

  // Sync and UI state
  const [isSyncing, setIsSyncing] = useState(false);
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Notification read-tracking state persisted in localStorage
  const [readLogIds, setReadLogIds] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem('tracked_read_notification_ids');
      return saved ? new Set(JSON.parse(saved)) : new Set();
    } catch {
      return new Set();
    }
  });

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  // 1. Fetch initial platform settings, logs, tracked tasks, and subscription
  const loadInitialData = useCallback(async () => {
    try {
      const [sett, disc, logs, tList, sub] = await Promise.all([
        api.fetchSettings(),
        api.fetchDiscoveryStatus(),
        api.fetchAuditLogs(),
        api.fetchTasks(),
        api.fetchSubscriptionInfo().catch(() => null),
      ]);
      setSettings(sett);
      setDiscoveryStatus(disc);
      setAuditLogs(logs);
      setTasks(tList);
      if (sub?.tier) {
        setPlanTier(sub.tier);
      }
    } catch (err: any) {
      console.error('Failed to load initial platform metadata:', err);
    }
  }, []);

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('billing') === 'success') {
      showToast('🎉 Subscription confirmed! Welcome to Pro.');
      setActiveTab('billing');
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (urlParams.get('billing') === 'cancel') {
      showToast('Checkout was cancelled. No charges were made.');
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  // 2. Fetch discovered issues for the Issue Finder
  const loadIssues = useCallback(async (filters: Record<string, any> = {}, size: number = 25) => {
    setLoadingIssues(true);
    setCurrentPage(1);
    try {
      const res = await api.fetchIssues({
        page: 1,
        page_size: size,
        ...filters,
      });
      setIssues(res.items || []);
      setTotalIssues(res.total || 0);
    } catch (err) {
      console.error('Failed to load issues for finder:', err);
    } finally {
      setLoadingIssues(false);
    }
  }, []);

  // 3. Load next page of issues (Load More / Auto-load)
  const handleLoadMoreIssues = useCallback(async () => {
    if (loadingIssues || loadingMoreIssues) return;
    if (issues.length >= totalIssues) return;

    setLoadingMoreIssues(true);
    const nextPage = Math.floor(issues.length / pageSize) + 1;
    try {
      const res = await api.fetchIssues({
        page: nextPage,
        page_size: pageSize,
        ...issueFilters,
      });
      if (res.items && res.items.length > 0) {
        setIssues(prev => {
          const existingIds = new Set(prev.map(i => i.id));
          const newItems = res.items.filter(i => !existingIds.has(i.id));
          return [...prev, ...newItems];
        });
        setCurrentPage(nextPage);
      }
      setTotalIssues(res.total || 0);
    } catch (err) {
      console.error('Failed to load more issues:', err);
    } finally {
      setLoadingMoreIssues(false);
    }
  }, [loadingIssues, loadingMoreIssues, issues.length, totalIssues, pageSize, issueFilters]);

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize);
    loadIssues(issueFilters, newSize);
  };

  const refreshTasks = useCallback(async () => {
    try {
      const tList = await api.fetchTasks();
      setTasks(tList);
    } catch (err) {
      console.error('Failed to refresh tasks:', err);
    }
  }, []);

  useEffect(() => {
    loadInitialData();
    loadIssues();

    // PWA Install listener
    const onInstallable = () => setIsInstallable(true);
    const onInstalled = () => setIsInstallable(false);
    window.addEventListener('pwa-installable', onInstallable);
    window.addEventListener('pwa-installed', onInstalled);

    // Background polling every 12 seconds to keep live states fresh
    const interval = setInterval(() => {
      api.fetchTasks().then(setTasks).catch(() => {});
      api.fetchAuditLogs().then(setAuditLogs).catch(() => {});
    }, 12000);

    return () => {
      clearInterval(interval);
      window.removeEventListener('pwa-installable', onInstallable);
      window.removeEventListener('pwa-installed', onInstalled);
    };
  }, [loadInitialData, loadIssues]);

  const handleInstallPWA = async () => {
    const accepted = await promptPWAInstall();
    if (accepted) {
      showToast('✓ Installing IssueToPR PWA to your device...');
    }
  };

  // Track any new GitHub URL (Issue or PR)
  const handleTrackUrl = async (url: string) => {
    try {
      showToast('Querying GitHub & adding to tracker...');
      const task = await api.trackItem(url);
      setTasks(prev => {
        const idx = prev.findIndex(t => t.id === task.id);
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = task;
          return updated;
        }
        return [task, ...prev];
      });
      showToast(`✓ Tracking ${task.issue?.repository?.full_name} #${task.pr_number || task.issue?.issue_number}`);
      api.fetchAuditLogs().then(setAuditLogs).catch(() => {});
    } catch (err: any) {
      showToast(`Track error: ${err.message}`);
      throw err;
    }
  };

  // Sync a single tracked item
  const handleSyncItem = async (taskId: string) => {
    try {
      const updated = await api.syncPRStatus(taskId);
      setTasks(prev => prev.map(t => t.id === updated.id ? updated : t));
      showToast(`✓ Synced live state for #${updated.pr_number || updated.issue?.issue_number}`);
      api.fetchAuditLogs().then(setAuditLogs).catch(() => {});
    } catch (err: any) {
      showToast(`Sync failed: ${err.message}`);
    }
  };

  // Untrack an item
  const handleUntrackItem = async (taskId: string) => {
    try {
      await api.untrackItem(taskId);
      setTasks(prev => prev.filter(t => t.id !== taskId));
      showToast('✓ Removed item from tracking');
      api.fetchAuditLogs().then(setAuditLogs).catch(() => {});
    } catch (err: any) {
      showToast(`Untrack failed: ${err.message}`);
    }
  };

  // Select an issue from Issue Finder to track/work on
  const handleSelectIssue = async (issueId: string) => {
    try {
      showToast('Tracking selected issue in dashboard...');
      const task = await api.selectIssue(issueId);
      await refreshTasks();
      showToast(`✓ Issue #${task.issue?.issue_number || ''} added to Tracked Items!`);
      setActiveTab('tracker');
      api.fetchAuditLogs().then(setAuditLogs).catch(() => {});
    } catch (err: any) {
      const msg = err.message || '';
      if (msg.includes('limit') || msg.includes('quota') || msg.includes('402') || msg.includes('QUOTA_EXCEEDED')) {
        setUpgradeReason(msg);
        setUpgradeModalOpen(true);
      } else {
        showToast(`Notice: ${msg}`);
      }
    }
  };

  // Mark an issue as complete in finder
  const handleCompleteIssue = async (issueId: string) => {
    const target = issues.find(i => i.id === issueId);

    // 1. Immediate optimistic removal from UI state
    setIssues(prev => prev.filter(i => {
      if (i.id === issueId) return false;
      if (target?.html_url && i.html_url === target.html_url) return false;
      return true;
    }));
    setTotalIssues(prev => Math.max(0, prev - 1));

    // 2. Persist completion in localStorage & backend
    try {
      await api.completeIssue(issueId, target);
      showToast('✓ Issue marked as completed and removed from finder.');
      api.fetchAuditLogs().then(setAuditLogs).catch(() => {});
    } catch (err: any) {
      showToast(`Error: ${err.message}`);
      loadIssues(issueFilters);
    }
  };

  // Handle filter change in Issue Finder
  const handleFilterChange = (filters: Record<string, any>) => {
    setIssueFilters(filters);
    loadIssues(filters, pageSize);
  };

  // Import authored pull requests from GitHub
  const handleImportAuthorPRs = async (username?: string) => {
    try {
      showToast('Searching GitHub for your pull requests...');
      const res = await api.importAuthorPRs(username);
      await refreshTasks();
      showToast(`✓ Found ${res.found_on_github} PRs, imported ${res.imported} to dashboard!`);
      api.fetchAuditLogs().then(setAuditLogs).catch(() => {});
    } catch (err: any) {
      showToast(`Import failed: ${err.message}`);
      throw err;
    }
  };

  // Sync all tracked items with GitHub
  const handleSyncAll = async () => {
    setIsSyncing(true);
    showToast('Syncing all tracked PRs and issues with GitHub...');
    try {
      const res = await api.syncAllTracker();
      const updated = await api.fetchTasks();
      setTasks(updated);
      showToast(`✓ Synced ${res.total_active ?? (res.synced_prs + res.synced_issues)} tracked items!`);
      api.fetchAuditLogs().then(setAuditLogs).catch(() => {});
    } catch (err: any) {
      showToast(`Sync error: ${err.message}`);
    } finally {
      setIsSyncing(false);
    }
  };

  // Notifications: Mark all as read
  const handleMarkAllRead = () => {
    const allIds = new Set(auditLogs.map(l => l.id));
    setReadLogIds(allIds);
    try {
      localStorage.setItem('tracked_read_notification_ids', JSON.stringify([...allIds]));
    } catch {}
    showToast('✓ All notifications marked as read');
  };

  // Notifications: Clear all
  const handleClearAllNotifications = async () => {
    try {
      await api.clearAuditLogs();
      setAuditLogs([]);
      setReadLogIds(new Set());
      try {
        localStorage.removeItem('tracked_read_notification_ids');
      } catch {}
      showToast('✓ All notifications cleared');
    } catch (err: any) {
      showToast(`Failed to clear: ${err.message}`);
    }
  };

  // Notifications: Delete single
  const handleDeleteNotification = async (logId: string) => {
    try {
      await api.deleteAuditLog(logId);
      setAuditLogs(prev => prev.filter(l => l.id !== logId));
    } catch (err: any) {
      showToast(`Failed to delete notification: ${err.message}`);
    }
  };

  const totalPRs = tasks.filter(t => Boolean(t.pr_number || t.pr_url)).length;
  const unreadNotificationsCount = auditLogs.filter(l => !readLogIds.has(l.id)).length;

  return (
    <div className="min-h-screen bg-[#080c14] text-neutral-100 flex font-sans selection:bg-blue-500 selection:text-white relative overflow-x-hidden">
        {/* Atmospheric Liquid Ambient Glow Orbs */}
        <div className="fixed inset-0 pointer-events-none overflow-hidden z-0" style={{ contain: 'strict' }}>
          <div className="ambient-orb-indigo -top-32 -left-32 opacity-25" />
          <div className="ambient-orb-cyan top-1/4 -right-32 opacity-20" />
          <div className="ambient-orb-emerald -bottom-32 left-1/3 opacity-15" />
        </div>

        {/* Toast Notification */}
        {toastMessage && (
          <div className="fixed bottom-24 sm:bottom-6 right-4 sm:right-6 z-50 bg-[#0c101a] border border-white/20 text-white px-4 py-3 rounded-2xl shadow-2xl text-xs flex items-center gap-2.5 animate-bounce">
            <ShieldCheck className="w-4 h-4 text-cyan-400 shrink-0" />
            <span>{toastMessage}</span>
          </div>
        )}

        {/* Persistent Left Sidebar (Desktop) - Locked Fixed Position */}
        <div className="hidden md:block w-64 shrink-0">
          <Sidebar
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            totalIssues={totalIssues}
            totalPRs={totalPRs}
            trackedTasksCount={tasks.length}
            onOpenUpgrade={() => setUpgradeModalOpen(true)}
          />
        </div>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-w-0 min-h-screen">
          {/* Top Header */}
          <Header
            discoveryStatus={discoveryStatus}
            settings={settings}
            onRefreshDiscovery={handleSyncAll}
            isSyncing={isSyncing}
            activeTab={activeTab}
            setActiveTab={setActiveTab as any}
            onLock={api.logout}
            isInstallable={isInstallable}
            onInstallPWA={handleInstallPWA}
            planTier={planTier}
          />

          {/* Main Content Container */}
          <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-6 pb-28 md:pb-12">
          {activeTab === 'issues' && (
            <IssueInbox
              issues={issues}
              loading={loadingIssues}
              loadingMore={loadingMoreIssues}
              hasMore={issues.length < totalIssues}
              onLoadMore={handleLoadMoreIssues}
              pageSize={pageSize}
              onPageSizeChange={handlePageSizeChange}
              totalIssues={totalIssues}
              onSelectIssue={handleSelectIssue}
              onOpenDetails={(issue) => setSelectedIssueModal(issue)}
              onCompleteIssue={handleCompleteIssue}
              onFilterChange={handleFilterChange}
            />
          )}

          {activeTab === 'bounties' && (
            <BountiesView
              onNavigateToTracker={() => setActiveTab('tracker')}
              onStartBountyWork={(_res) => {
                refreshTasks();
                setActiveTab('tracker');
              }}
            />
          )}

          {activeTab === 'tracker' && (
            <TrackedIssuesView
              tasks={tasks}
              onTrackUrl={handleTrackUrl}
              onSyncItem={handleSyncItem}
              onUntrackItem={handleUntrackItem}
              onImportAuthorPRs={handleImportAuthorPRs}
            />
          )}

          {activeTab === 'prs' && (
            <PullRequestsView
              tasks={tasks}
              onRefreshTasks={refreshTasks}
              onUntrackItem={handleUntrackItem}
              onImportAuthorPRs={handleImportAuthorPRs}
            />
          )}

          {activeTab === 'history' && (
            <ActivityHistoryView logs={auditLogs} />
          )}

          {activeTab === 'runners' && (
            <RunnersView />
          )}

          {activeTab === 'billing' && (
            <BillingView />
          )}

          {activeTab === 'settings' && (
            <SettingsView
              settings={settings}
              onSaveSettings={async (updated) => {
                const res = await api.updateSettings(updated);
                setSettings(res);
                showToast('✓ Settings updated successfully');
              }}
            />
          )}
        </main>

        {/* Mobile Bottom Navigation Bar (iOS / Android Style) */}
        <nav className="sm:hidden fixed bottom-0 left-0 right-0 z-50 bg-white/90 dark:bg-[#030303]/95 backdrop-blur-2xl border-t border-slate-200 dark:border-white/10 px-2 py-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-2xl shadow-slate-900/10 dark:shadow-black">
          <div className="grid grid-cols-7 gap-1 text-[10px] font-medium text-center">
            {/* 1. Find Issues */}
            <button
              onClick={() => setActiveTab('issues')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'issues'
                  ? 'text-indigo-600 bg-indigo-50 border border-indigo-200 dark:text-white dark:bg-neutral-900 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              <div className="relative">
                <Search className="w-5 h-5 mb-0.5" />
                {totalIssues > 0 && (
                  <span className="absolute -top-1 -right-2 px-1.5 py-0.2 rounded-full bg-slate-900 text-white dark:bg-white dark:text-black text-[9px] font-bold">
                    {totalIssues > 99 ? '99+' : totalIssues}
                  </span>
                )}
              </div>
              <span>Issues</span>
            </button>

            {/* 2. Bounties */}
            <button
              onClick={() => setActiveTab('bounties')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'bounties'
                  ? 'text-amber-600 bg-amber-50 border border-amber-200 dark:text-amber-400 dark:bg-amber-950/40 dark:border-amber-500/30 font-bold'
                  : 'text-slate-500 hover:text-amber-600 dark:text-neutral-400 dark:hover:text-amber-300'
              }`}
            >
              <div className="relative">
                <Coins className="w-5 h-5 mb-0.5 text-amber-500 dark:text-amber-400" />
              </div>
              <span>Bounties</span>
            </button>

            {/* 3. Tracked */}
            <button
              onClick={() => setActiveTab('tracker')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'tracker'
                  ? 'text-purple-600 bg-purple-50 border border-purple-200 dark:text-white dark:bg-neutral-900 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              <div className="relative">
                <Layers className="w-5 h-5 mb-0.5" />
                {tasks.length > 0 && (
                  <span className="absolute -top-1 -right-2 px-1.5 py-0.2 rounded-full bg-slate-900 text-white dark:bg-white dark:text-black text-[9px] font-bold">
                    {tasks.length}
                  </span>
                )}
              </div>
              <span>Tracked</span>
            </button>

            {/* 3. Pull Requests */}
            <button
              onClick={() => setActiveTab('prs')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'prs'
                  ? 'text-teal-600 bg-teal-50 border border-teal-200 dark:text-white dark:bg-neutral-900 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              <div className="relative">
                <GitPullRequest className="w-5 h-5 mb-0.5" />
                {totalPRs > 0 && (
                  <span className="absolute -top-1 -right-2 px-1.5 py-0.2 rounded-full bg-slate-900 text-white dark:bg-white dark:text-black text-[9px] font-bold">
                    {totalPRs}
                  </span>
                )}
              </div>
              <span>PRs</span>
            </button>

            {/* 4. Timeline */}
            <button
              onClick={() => setActiveTab('history')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'history'
                  ? 'text-amber-600 bg-amber-50 border border-amber-200 dark:text-white dark:bg-neutral-900 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              <History className="w-5 h-5 mb-0.5" />
              <span>Timeline</span>
            </button>

            {/* 5. Runners */}
            <button
              onClick={() => setActiveTab('runners')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'runners'
                  ? 'text-cyan-600 bg-cyan-50 border border-cyan-200 dark:text-white dark:bg-neutral-900 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              <Cpu className="w-5 h-5 mb-0.5" />
              <span>Runners</span>
            </button>

            {/* 6. Billing */}
            <button
              onClick={() => setActiveTab('billing')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'billing'
                  ? 'text-rose-600 bg-rose-50 border border-rose-200 dark:text-white dark:bg-neutral-900 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              <CreditCard className="w-5 h-5 mb-0.5" />
              <span>Billing</span>
            </button>

            {/* 7. Settings */}
            <button
              onClick={() => setActiveTab('settings')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'settings'
                  ? 'text-slate-900 bg-slate-200 border border-slate-300 dark:text-white dark:bg-neutral-900 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              <SettingsIcon className="w-5 h-5 mb-0.5" />
              <span>Settings</span>
            </button>
          </div>
        </nav>
      </div>

        {/* Issue Details Modal */}
        {selectedIssueModal && (
          <IssueDetailsModal
            issue={selectedIssueModal}
            onClose={() => setSelectedIssueModal(null)}
            onSelectIssue={(id) => {
              handleSelectIssue(id);
              setSelectedIssueModal(null);
            }}
            onCompleteIssue={(id) => {
              handleCompleteIssue(id);
              setSelectedIssueModal(null);
            }}
          />
        )}

        {/* Pro Upgrade & Quota Modal */}
        <UpgradeModal
          isOpen={upgradeModalOpen}
          onClose={() => setUpgradeModalOpen(false)}
          reason={upgradeReason}
          onNavigateToBilling={() => setActiveTab('billing')}
        />

        {/* Notifications Drawer */}
        <NotificationsPanel
          isOpen={isNotificationsOpen}
          onClose={() => setIsNotificationsOpen(false)}
          logs={auditLogs}
          readLogIds={readLogIds}
          onMarkAllRead={handleMarkAllRead}
          onClearAll={handleClearAllNotifications}
          onDeleteLog={handleDeleteNotification}
          onNavigate={(tab) => {
            setActiveTab(tab as any);
            setIsNotificationsOpen(false);
          }}
        />
      </div>
  );
}

export default App;
