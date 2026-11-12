import React, { useState, useEffect, useCallback, useRef, Suspense, lazy } from 'react';
import { 
  Layers, GitPullRequest, ShieldCheck, Search, 
  Coins, Menu, Share2, X
} from 'lucide-react';

import { Issue, Task, PlatformSettings, DiscoveryStatus, AuditLog, SubscriptionInfo } from './types';
import * as api from './api';

import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { IssueInbox } from './components/IssueInbox';
import { NotificationsPanel } from './components/NotificationsPanel';
import { MobileDrawer } from './components/MobileDrawer';
import { promptPWAInstall } from './registerSW';

// Lazy-loaded secondary views for high performance & minimal bundle size
const TrackedIssuesView = lazy(() => import('./components/TrackedIssuesView').then(m => ({ default: m.TrackedIssuesView })));
const PullRequestsView = lazy(() => import('./components/PullRequestsView').then(m => ({ default: m.PullRequestsView })));
const ActivityHistoryView = lazy(() => import('./components/ActivityHistoryView').then(m => ({ default: m.ActivityHistoryView })));
const RunnersView = lazy(() => import('./components/RunnersView').then(m => ({ default: m.RunnersView })));
const BillingView = lazy(() => import('./components/BillingView').then(m => ({ default: m.BillingView })));
const SettingsView = lazy(() => import('./components/SettingsView').then(m => ({ default: m.SettingsView })));
const AdminConsoleView = lazy(() => import('./components/AdminConsoleView').then(m => ({ default: m.AdminConsoleView })));
const IssueDetailsModal = lazy(() => import('./components/IssueDetailsModal').then(m => ({ default: m.IssueDetailsModal })));
const UpgradeModal = lazy(() => import('./components/UpgradeModal').then(m => ({ default: m.UpgradeModal })));
const SupportUpiModal = lazy(() => import('./components/SupportUpiModal').then(m => ({ default: m.SupportUpiModal })));

function TabLoadingSkeleton() {
  return (
    <div className="w-full py-20 flex flex-col items-center justify-center space-y-3 animate-fade-in">
      <div className="w-8 h-8 rounded-full border-2 border-blue-500/20 border-t-blue-500 animate-spin" />
      <span className="text-xs font-mono text-slate-400 dark:text-neutral-500">Loading module...</span>
    </div>
  );
}

export function App() {
  const [activeTab, setActiveTab] = useState<'issues' | 'tracker' | 'prs' | 'history' | 'runners' | 'billing' | 'settings' | 'admin'>('issues');
  const [isInstallable, setIsInstallable] = useState(false);
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = useState(false);
  const [planTier, setPlanTier] = useState<string>('pro');
  const [subscriptionInfo, setSubscriptionInfo] = useState<SubscriptionInfo | null>(null);
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [upgradeReason, setUpgradeReason] = useState<string | undefined>(undefined);
  const [supportUpiModalOpen, setSupportUpiModalOpen] = useState(false);
  const [settingsSection, setSettingsSection] = useState<'github' | 'ai' | 'automation' | 'skills' | 'team' | 'workspace' | 'account'>('github');

  // iOS Safari "Add to Home Screen" detection
  const [showIosInstallGuide, setShowIosInstallGuide] = useState(() => {
    try {
      const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream;
      const isStandalone = window.matchMedia('(display-mode: standalone)').matches || (navigator as any).standalone;
      const dismissed = localStorage.getItem('dismissed_ios_install_guide');
      return isIos && !isStandalone && !dismissed;
    } catch {
      return false;
    }
  });

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
  const [issueFilters, setIssueFilters] = useState<Record<string, any>>({ availability: 'available', unassigned_only: true });

  // Sync and UI state
  const [isSyncing, setIsSyncing] = useState(false);
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Collapsible Sidebar State (persisted across sessions)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem('issue_to_pr_sidebar_collapsed') === 'true';
    } catch {
      return false;
    }
  });

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarCollapsed(prev => {
      const next = !prev;
      try {
        localStorage.setItem('issue_to_pr_sidebar_collapsed', String(next));
      } catch {}
      return next;
    });
  }, []);

  // Quick keyboard shortcut: Ctrl+B or Cmd+B to toggle sidebar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        handleToggleSidebar();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleToggleSidebar]);

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
      if (sub) {
        setSubscriptionInfo(sub);
        if (sub.tier) {
          setPlanTier(sub.tier);
        }
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
      const fetched = res.items || [];
      setIssues(fetched);
      setTotalIssues(res.total || 0);
      return { count: fetched.length, total: res.total || 0 };
    } catch (err) {
      console.error('Failed to load issues for finder:', err);
      return { count: 0, total: 0 };
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

  const hasAutoScannedRef = useRef(false);

  const runLoginDiscoveryScan = useCallback(async () => {
    if (hasAutoScannedRef.current) return;
    hasAutoScannedRef.current = true;
    try {
      sessionStorage.setItem('issuetopr_login_scan_ran', '1');
    } catch {}

    window.dispatchEvent(new CustomEvent('issuetopr-cron-started'));
    showToast('🔍 Auto-running 2h GSoC issue scan after sign-in...');
    try {
      const scanRes = await api.triggerCronRunNow();
      await loadIssues(issueFilters, pageSize);
      window.dispatchEvent(new CustomEvent('issuetopr-cron-completed', { detail: scanRes }));
      const synced = scanRes?.last_issues_synced ?? scanRes?.discovered ?? 0;
      showToast(`✓ 2h GSoC scan complete: synced ${synced} open issues.`);
    } catch (err) {
      console.warn('Auto login discovery scan warning:', err);
      window.dispatchEvent(new CustomEvent('issuetopr-cron-completed', { detail: null }));
    }
  }, [issueFilters, loadIssues, pageSize]);

  useEffect(() => {
    let active = true;
    loadInitialData();
    loadIssues({ availability: 'available', unassigned_only: true }).then((result) => {
      if (!active) return;
      let alreadyScanned = false;
      try {
        alreadyScanned = sessionStorage.getItem('issuetopr_login_scan_ran') === '1';
      } catch {}
      if (!alreadyScanned || result.count === 0) {
        void runLoginDiscoveryScan();
      }
    });

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
      active = false;
      clearInterval(interval);
      window.removeEventListener('pwa-installable', onInstallable);
      window.removeEventListener('pwa-installed', onInstalled);
    };
  }, [loadInitialData, loadIssues, runLoginDiscoveryScan]);

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
      if (res.tasks && res.tasks.length > 0) {
        setTasks(prev => {
          const importedIds = new Set(res.tasks!.map((t: any) => t.id || t.pr_url));
          const filtered = prev.filter(p => !importedIds.has(p.id) && !importedIds.has(p.pr_url));
          return [...res.tasks!, ...filtered];
        });
      } else {
        const updatedTasks = await api.fetchTasks();
        setTasks(updatedTasks);
      }
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
    <div 
      className="min-h-screen bg-[#080c14] text-neutral-100 flex font-sans selection:bg-blue-500 selection:text-white relative overflow-x-clip"
    >
        {/* Atmospheric Liquid Ambient Glow Orbs (Desktop Only - Disabled on mobile to lock 120 FPS) */}
        <div className="fixed inset-0 pointer-events-none overflow-hidden z-0 hidden md:block" style={{ contain: 'strict' }}>
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

        {/* Persistent Left Sidebar (Desktop) - Collapsible & Viewport-Locked */}
        <div className={`hidden md:block transition-all duration-300 ease-in-out shrink-0 ${isSidebarCollapsed ? 'w-20' : 'w-64'}`}>
          <Sidebar
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            totalIssues={totalIssues}
            totalPRs={totalPRs}
            trackedTasksCount={tasks.length}
            onOpenUpgrade={() => setUpgradeModalOpen(true)}
            onOpenSupportUpi={() => setSupportUpiModalOpen(true)}
            isCollapsed={isSidebarCollapsed}
            onToggleCollapse={handleToggleSidebar}
            subscriptionInfo={subscriptionInfo}
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
            onOpenSupportUpi={() => setSupportUpiModalOpen(true)}
            onOpenTeamSettings={() => {
              setSettingsSection('team');
              setActiveTab('settings');
            }}
            isInstallable={isInstallable}
            onInstallPWA={handleInstallPWA}
            onToggleMobileMenu={() => setIsMobileDrawerOpen(prev => !prev)}
            planTier={planTier}
            subscriptionInfo={subscriptionInfo}
          />

          {/* Main Content Container */}
          <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-6 pb-28 md:pb-12">
            <Suspense fallback={<TabLoadingSkeleton />}>
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

              {activeTab === 'admin' && (
                <AdminConsoleView
                  subscriptionInfo={subscriptionInfo}
                  onSubscriptionUpdated={async (tier) => {
                    setPlanTier(tier);
                    const latest = await api.fetchSubscriptionInfo().catch(() => null);
                    if (latest) {
                      setSubscriptionInfo(latest);
                    }
                  }}
                />
              )}

              {activeTab === 'settings' && (
                <SettingsView
                  settings={settings}
                  initialSection={settingsSection}
                  onSettingsUpdated={(updated) => setSettings(updated)}
                  onSaveSettings={async (updated) => {
                    const res = await api.updateSettings(updated);
                    setSettings(res);
                    showToast('✓ Settings updated successfully');
                  }}
                />
              )}
            </Suspense>
          </main>

        {/* iOS Safari PWA Install Instruction Banner */}
        {showIosInstallGuide && (
          <aside aria-label="Install App" className="fixed bottom-20 left-4 right-4 z-50 p-4 rounded-2xl bg-slate-900/95 dark:bg-neutral-900/95 text-white backdrop-blur-xl border border-white/20 shadow-2xl animate-fade-in flex items-start gap-3 md:hidden">
            <div className="w-9 h-9 rounded-xl bg-blue-500/20 text-blue-400 border border-blue-400/30 flex items-center justify-center shrink-0 mt-0.5">
              <Share2 className="w-5 h-5" />
            </div>
            <div className="flex-1 text-xs space-y-1">
              <div className="font-bold text-sm flex items-center justify-between">
                <span>Install Issue-to-PR App</span>
                <button
                  type="button"
                  onClick={() => {
                    setShowIosInstallGuide(false);
                    try { localStorage.setItem('dismissed_ios_install_guide', 'true'); } catch {}
                  }}
                  className="p-1 text-neutral-400 hover:text-white rounded-lg transition"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <p className="text-neutral-300 leading-relaxed">
                Tap the <strong className="text-white">Share</strong> button in Safari's toolbar, then scroll down and tap <strong className="text-white">"Add to Home Screen"</strong>.
              </p>
            </div>
          </aside>
        )}

        {/* Mobile Bottom Navigation Bar (iOS / Android Ergonomic 4-Tab Bar - GPU Accelerated) */}
        <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-white/95 dark:bg-[#030303]/95 backdrop-blur-md border-t border-slate-200 dark:border-white/10 px-2 py-1.5 pb-[max(0.5rem,env(safe-area-inset-bottom))] shadow-lg shadow-slate-900/5 dark:shadow-black/40 transform-gpu gpu-layer">
          <div className="grid grid-cols-4 gap-1 text-[11px] font-medium text-center">
            {/* 1. Find Issues */}
            <button
              onClick={() => setActiveTab('issues')}
              className={`flex flex-col items-center justify-center py-1.5 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'issues'
                  ? 'text-blue-600 bg-blue-50 border border-blue-200 dark:text-white dark:bg-white/10 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white'
              }`}
            >
              <div className="relative">
                <Search className="w-5 h-5 mb-0.5" />
                {totalIssues > 0 && (
                  <span className="absolute -top-1 -right-2 px-1.5 py-0.2 rounded-full bg-blue-600 text-white dark:bg-white dark:text-black text-[9px] font-bold">
                    {totalIssues > 99 ? '99+' : totalIssues}
                  </span>
                )}
              </div>
              <span>Issues</span>
            </button>

            {/* 2. Tracked Items */}
            <button
              onClick={() => setActiveTab('tracker')}
              className={`flex flex-col items-center justify-center py-1.5 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'tracker'
                  ? 'text-purple-600 bg-purple-50 border border-purple-200 dark:text-white dark:bg-white/10 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white'
              }`}
            >
              <div className="relative">
                <Layers className="w-5 h-5 mb-0.5" />
                {tasks.length > 0 && (
                  <span className="absolute -top-1 -right-2 px-1.5 py-0.2 rounded-full bg-purple-600 text-white dark:bg-white dark:text-black text-[9px] font-bold">
                    {tasks.length}
                  </span>
                )}
              </div>
              <span>Tracked</span>
            </button>

            {/* 4. Pull Requests */}
            <button
              onClick={() => setActiveTab('prs')}
              className={`flex flex-col items-center justify-center py-1.5 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'prs'
                  ? 'text-teal-600 bg-teal-50 border border-teal-200 dark:text-white dark:bg-white/10 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white'
              }`}
            >
              <div className="relative">
                <GitPullRequest className="w-5 h-5 mb-0.5" />
                {totalPRs > 0 && (
                  <span className="absolute -top-1 -right-2 px-1.5 py-0.2 rounded-full bg-teal-600 text-white dark:bg-white dark:text-black text-[9px] font-bold">
                    {totalPRs}
                  </span>
                )}
              </div>
              <span>PRs</span>
            </button>

            {/* 5. More Menu Drawer Toggle */}
            <button
              onClick={() => setIsMobileDrawerOpen(true)}
              className={`flex flex-col items-center justify-center py-1.5 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                ['history', 'runners', 'billing', 'settings', 'admin'].includes(activeTab) || isMobileDrawerOpen
                  ? 'text-blue-600 bg-blue-50 border border-blue-200 dark:text-white dark:bg-white/10 dark:border-white/20 font-bold'
                  : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white'
              }`}
              title="More views, settings, and device runners"
            >
              <div className="relative">
                <Menu className="w-5 h-5 mb-0.5" />
                {['history', 'runners', 'billing', 'settings', 'admin'].includes(activeTab) && (
                  <span className="absolute -top-0.5 -right-1 w-2 h-2 rounded-full bg-blue-500 ring-2 ring-white dark:ring-black" />
                )}
              </div>
              <span>More</span>
            </button>
          </div>
        </nav>

        {/* Mobile Slide-Over Navigation Drawer */}
        <MobileDrawer
          isOpen={isMobileDrawerOpen}
          onClose={() => setIsMobileDrawerOpen(false)}
          activeTab={activeTab}
          setActiveTab={setActiveTab as any}
          isInstallable={isInstallable}
          onInstallPWA={handleInstallPWA}
          onLock={api.logout}
          onOpenSupportUpi={() => setSupportUpiModalOpen(true)}
          onOpenTeamSettings={() => {
            setSettingsSection('team');
            setActiveTab('settings');
          }}
          planTier={planTier}
          subscriptionInfo={subscriptionInfo}
        />
      </div>

        {/* Lazy-Loaded Modals */}
        <Suspense fallback={null}>
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
            subscriptionInfo={subscriptionInfo}
          />

          {/* Direct UPI Support / Donate Modal */}
          <SupportUpiModal
            isOpen={supportUpiModalOpen}
            onClose={() => setSupportUpiModalOpen(false)}
            onNavigateToBilling={() => setActiveTab('billing')}
            onPaymentSubmitted={(req) => {
              showToast(`✓ UPI Ref ${req.utr_number} (₹${req.amount_inr}) submitted!`);
            }}
          />
        </Suspense>

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
