import React, { useState, useEffect, useCallback } from 'react';
import { 
  Layers, GitPullRequest, Settings as SettingsIcon, History, 
  ShieldCheck, Search, Cpu
} from 'lucide-react';

import { Issue, Task, PlatformSettings, DiscoveryStatus, AuditLog } from './types';
import * as api from './api';

import { Header } from './components/Header';
import { IssueInbox } from './components/IssueInbox';
import { IssueDetailsModal } from './components/IssueDetailsModal';
import { TrackedIssuesView } from './components/TrackedIssuesView';
import { PullRequestsView } from './components/PullRequestsView';
import { ActivityHistoryView } from './components/ActivityHistoryView';
import { RunnersView } from './components/RunnersView';
import { SettingsView } from './components/SettingsView';
import { NotificationsPanel } from './components/NotificationsPanel';
import { promptPWAInstall } from './registerSW';

export function App() {
  const [activeTab, setActiveTab] = useState<'issues' | 'tracker' | 'prs' | 'history' | 'runners' | 'settings'>('issues');
  const [isInstallable, setIsInstallable] = useState(false);

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

  // 1. Fetch initial platform settings, logs, and tracked tasks
  const loadInitialData = useCallback(async () => {
    try {
      const [sett, disc, logs, tList] = await Promise.all([
        api.fetchSettings(),
        api.fetchDiscoveryStatus(),
        api.fetchAuditLogs(),
        api.fetchTasks(),
      ]);
      setSettings(sett);
      setDiscoveryStatus(disc);
      setAuditLogs(logs);
      setTasks(tList);
    } catch (err: any) {
      console.error('Failed to load initial platform metadata:', err);
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
    const nextPage = currentPage + 1;
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
  }, [loadingIssues, loadingMoreIssues, issues.length, totalIssues, currentPage, pageSize, issueFilters]);

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
      showToast(`Notice: ${err.message}`);
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
    <div className="min-h-screen bg-[#000000] text-neutral-100 flex flex-col font-sans selection:bg-white selection:text-black">
        {/* Toast Notification */}
        {toastMessage && (
          <div className="fixed bottom-24 sm:bottom-6 right-4 sm:right-6 z-50 bg-[#080808] border border-white/20 text-white px-4 py-3 rounded-2xl shadow-2xl text-xs flex items-center gap-2.5 animate-bounce">
            <ShieldCheck className="w-4 h-4 text-white shrink-0" />
            <span>{toastMessage}</span>
          </div>
        )}

        {/* Header */}
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
        />

        {/* Desktop Top Navigation Bar (Hidden on Mobile) */}
        <nav className="hidden sm:block bg-[#000000] border-b border-white/10 sticky top-16 z-30 backdrop-blur-md">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-1.5 sm:gap-2 overflow-x-auto py-2.5 text-xs font-medium no-scrollbar">
              {/* 1. Issue Finder */}
              <button
                onClick={() => setActiveTab('issues')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl transition-all duration-200 shrink-0 active:scale-95 ${
                  activeTab === 'issues'
                    ? 'bg-white text-black font-bold shadow-sm'
                    : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
                }`}
              >
                <Search className="w-4 h-4" />
                <span>Find Issues</span>
                {totalIssues > 0 && (
                  <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                    activeTab === 'issues' ? 'bg-black text-white' : 'bg-neutral-900 text-neutral-300 border border-white/20'
                  }`}>
                    {totalIssues}
                  </span>
                )}
              </button>

              {/* 2. Tracked Items */}
              <button
                onClick={() => setActiveTab('tracker')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl transition-all duration-200 shrink-0 active:scale-95 ${
                  activeTab === 'tracker'
                    ? 'bg-white text-black font-bold shadow-sm'
                    : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
                }`}
              >
                <Layers className="w-4 h-4" />
                <span>Tracked Items</span>
                <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                  activeTab === 'tracker' ? 'bg-black text-white' : 'bg-neutral-900 text-neutral-300 border border-white/20'
                }`}>
                  {tasks.length}
                </span>
              </button>

              {/* 3. Pull Requests */}
              <button
                onClick={() => setActiveTab('prs')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl transition-all duration-200 shrink-0 active:scale-95 ${
                  activeTab === 'prs'
                    ? 'bg-white text-black font-bold shadow-sm'
                    : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
                }`}
              >
                <GitPullRequest className="w-4 h-4" />
                <span>Pull Requests</span>
                {totalPRs > 0 && (
                  <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                    activeTab === 'prs' ? 'bg-black text-white' : 'bg-neutral-900 text-neutral-300 border border-white/20'
                  }`}>
                    {totalPRs}
                  </span>
                )}
              </button>

              {/* 4. Activity History */}
              <button
                onClick={() => setActiveTab('history')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl transition-all duration-200 shrink-0 active:scale-95 ${
                  activeTab === 'history'
                    ? 'bg-white text-black font-bold shadow-sm'
                    : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
                }`}
              >
                <History className="w-4 h-4" />
                <span>Activity Timeline</span>
              </button>

              {/* 5. Hybrid Runners */}
              <button
                onClick={() => setActiveTab('runners')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl transition-all duration-200 shrink-0 active:scale-95 ${
                  activeTab === 'runners'
                    ? 'bg-white text-black font-bold shadow-sm'
                    : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
                }`}
              >
                <Cpu className="w-4 h-4" />
                <span>Runners</span>
              </button>

              {/* 6. Settings */}
              <button
                onClick={() => setActiveTab('settings')}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl transition-all duration-200 shrink-0 ml-auto active:scale-95 ${
                  activeTab === 'settings'
                    ? 'bg-white text-black font-bold shadow-sm'
                    : 'text-neutral-400 hover:text-white hover:bg-neutral-900'
                }`}
              >
                <SettingsIcon className="w-4 h-4" />
                <span>Settings</span>
              </button>
            </div>
          </div>
        </nav>

        {/* Main Content Area */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-3 sm:px-6 lg:px-8 py-5 sm:py-8 pb-32 sm:pb-8">
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
        <nav className="sm:hidden fixed bottom-0 left-0 right-0 z-50 bg-[#030303]/95 backdrop-blur-2xl border-t border-white/10 px-2 py-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-2xl shadow-black">
          <div className="grid grid-cols-6 gap-1 text-[10px] font-medium text-center">
            {/* 1. Find Issues */}
            <button
              onClick={() => setActiveTab('issues')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'issues'
                  ? 'text-white bg-neutral-900 border border-white/20 font-bold'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              <div className="relative">
                <Search className="w-5 h-5 mb-0.5" />
                {totalIssues > 0 && (
                  <span className="absolute -top-1 -right-2 px-1.5 py-0.2 rounded-full bg-white text-black text-[9px] font-bold">
                    {totalIssues > 99 ? '99+' : totalIssues}
                  </span>
                )}
              </div>
              <span>Issues</span>
            </button>

            {/* 2. Tracked */}
            <button
              onClick={() => setActiveTab('tracker')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'tracker'
                  ? 'text-white bg-neutral-900 border border-white/20 font-bold'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              <div className="relative">
                <Layers className="w-5 h-5 mb-0.5" />
                {tasks.length > 0 && (
                  <span className="absolute -top-1 -right-2 px-1.5 py-0.2 rounded-full bg-white text-black text-[9px] font-bold">
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
                  ? 'text-white bg-neutral-900 border border-white/20 font-bold'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              <div className="relative">
                <GitPullRequest className="w-5 h-5 mb-0.5" />
                {totalPRs > 0 && (
                  <span className="absolute -top-1 -right-2 px-1.5 py-0.2 rounded-full bg-white text-black text-[9px] font-bold">
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
                  ? 'text-white bg-neutral-900 border border-white/20 font-bold'
                  : 'text-neutral-400 hover:text-neutral-200'
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
                  ? 'text-white bg-neutral-900 border border-white/20 font-bold'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              <Cpu className="w-5 h-5 mb-0.5" />
              <span>Runners</span>
            </button>

            {/* 6. Settings */}
            <button
              onClick={() => setActiveTab('settings')}
              className={`flex flex-col items-center justify-center py-2 px-1 rounded-xl transition min-h-[48px] active:scale-95 ${
                activeTab === 'settings'
                  ? 'text-white bg-neutral-900 border border-white/20 font-bold'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              <SettingsIcon className="w-5 h-5 mb-0.5" />
              <span>Settings</span>
            </button>
          </div>
        </nav>

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
