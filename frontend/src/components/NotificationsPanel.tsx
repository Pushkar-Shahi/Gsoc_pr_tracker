import React, { useState, useMemo } from 'react';
import { 
  X, Bell, CheckCircle2, AlertTriangle, Send, Terminal, Clock, 
  Trash2, CheckCheck, GitPullRequest, Sparkles, Filter, ExternalLink,
  ShieldCheck, RefreshCw, AlertCircle
} from 'lucide-react';
import { AuditLog } from '../types';

interface NotificationsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  logs: AuditLog[];
  readLogIds: Set<string>;
  onMarkAllRead: () => void;
  onClearAll: () => Promise<void>;
  onDeleteLog?: (id: string) => Promise<void>;
  onNavigate?: (tab: string) => void;
}

export const NotificationsPanel: React.FC<NotificationsPanelProps> = ({
  isOpen,
  onClose,
  logs,
  readLogIds,
  onMarkAllRead,
  onClearAll,
  onDeleteLog,
  onNavigate,
}) => {
  const [filterMode, setFilterMode] = useState<'all' | 'unread'>('all');
  const [isClearing, setIsClearing] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  if (!isOpen) return null;

  const unreadCount = logs.filter(l => !readLogIds.has(l.id)).length;

  const displayedLogs = useMemo(() => {
    if (filterMode === 'unread') {
      return logs.filter(l => !readLogIds.has(l.id));
    }
    return logs;
  }, [logs, filterMode, readLogIds]);

  const formatTimeAgo = (dateStr: string) => {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  const [notificationPermission, setNotificationPermission] = useState<string>(() => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      return Notification.permission;
    }
    return 'default';
  });

  const requestNotificationPermission = async () => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      try {
        const perm = await Notification.requestPermission();
        setNotificationPermission(perm);
        if (perm === 'granted') {
          new Notification('✓ Live Notifications Activated', {
            body: 'You will receive instant desktop alerts for PR status updates, review comments, and 2-hour scan sweeps.',
            icon: '/icons/icon-192.png'
          });
        }
      } catch {}
    }
  };

  const getEventMeta = (log: AuditLog) => {
    const action = log.action || '';
    if (action.includes('PR_MERGED')) {
      return {
        icon: <GitPullRequest className="w-4 h-4 text-white" />,
        badgeBg: 'bg-white/10 border-white/20 text-white font-bold',
        title: log.details?.pr_number ? `PR #${log.details.pr_number} Merged Upstream 🎉` : 'Pull Request Merged 🎉',
        desc: log.details?.merged_at 
          ? `Successfully merged into default branch upstream.` 
          : 'Pull request successfully integrated into upstream project.',
        tab: 'prs',
      };
    }
    if (action.includes('CHANGES_REQUESTED')) {
      return {
        icon: <AlertCircle className="w-4 h-4 text-white" />,
        badgeBg: 'bg-neutral-900 border-white/30 text-white',
        title: log.details?.pr_number ? `Review Changes on PR #${log.details.pr_number}` : 'Maintainer Requested Changes ⚠️',
        desc: 'Maintainer requested feedback adjustments on your pull request.',
        tab: 'prs',
      };
    }
    if (action.includes('PR_PUBLISHED')) {
      return {
        icon: <Send className="w-4 h-4 text-white" />,
        badgeBg: 'bg-neutral-900 border-white/20 text-neutral-200',
        title: 'Pull Request Published to GitHub',
        desc: log.details?.pr_url || 'PR branch submitted and live on GitHub.',
        tab: 'prs',
      };
    }
    if (action.includes('TRACKER_IMPORT') || action.includes('IMPORT')) {
      return {
        icon: <Sparkles className="w-4 h-4 text-white" />,
        badgeBg: 'bg-neutral-900 border-white/20 text-neutral-200',
        title: 'Author Pull Requests Imported',
        desc: log.details?.imported !== undefined
          ? `Imported ${log.details.imported} pull requests from GitHub author search.` 
          : (log.details?.message || 'Pull requests synced from GitHub.'),
        tab: 'prs',
      };
    }
    if (action.includes('TRACKER_ITEM_ADDED') || action.includes('TRACK')) {
      return {
        icon: <Sparkles className="w-4 h-4 text-white" />,
        badgeBg: 'bg-neutral-900 border-white/20 text-neutral-200',
        title: 'New Item Tracked',
        desc: log.details?.url || log.details?.title || 'GitHub item added to live tracking board.',
        tab: 'tracker',
      };
    }
    if (action.includes('VALIDATION')) {
      return {
        icon: <CheckCircle2 className="w-4 h-4 text-white" />,
        badgeBg: 'bg-neutral-900 border-white/20 text-neutral-200',
        title: 'CI & Local Validation Executed',
        desc: log.details?.message || 'Test suite and security diff checks finished.',
        tab: 'prs',
      };
    }
    if (action.includes('CRON_DISCOVERY')) {
      return {
        icon: <Clock className="w-4 h-4 text-white" />,
        badgeBg: 'bg-neutral-900 border-white/20 text-neutral-200',
        title: '2-Hour Cron Scan Completed ⏰',
        desc: `Synced ${log.details?.items_synced ?? 0} issues, pruned ${log.details?.items_pruned ?? 0} closed across NumFOCUS, PSF, DeepChem, and Kornia.`,
        tab: 'issues',
      };
    }
    if (action.includes('DISCOVERY')) {
      return {
        icon: <RefreshCw className="w-4 h-4 text-white" />,
        badgeBg: 'bg-neutral-900 border-white/20 text-neutral-200',
        title: 'Issue Discovery Synced',
        desc: log.details?.items_synced 
          ? `Synchronized ${log.details.items_synced} candidate issues.` 
          : 'Scanned target organizations for candidate issues.',
        tab: 'issues',
      };
    }
    if (action.includes('SETTINGS')) {
      return {
        icon: <ShieldCheck className="w-4 h-4 text-white" />,
        badgeBg: 'bg-neutral-900 border-white/20 text-neutral-300',
        title: 'Configuration Updated',
        desc: log.details?.github_token_set ? 'GitHub Personal Access Token updated.' : 'Platform settings saved.',
        tab: 'settings',
      };
    }

    return {
      icon: <Bell className="w-4 h-4 text-neutral-300" />,
      badgeBg: 'bg-neutral-900 border-white/10 text-neutral-300',
      title: action.replace(/_/g, ' '),
      desc: log.details?.message || log.details?.recommendation || `Event recorded (${log.actor})`,
      tab: 'tracker',
    };
  };

  const handleClearAllClick = async () => {
    if (!window.confirm('Clear all notifications from history?')) return;
    setIsClearing(true);
    try {
      await onClearAll();
    } finally {
      setIsClearing(false);
    }
  };

  const handleDeleteItem = async (e: React.MouseEvent, logId: string) => {
    e.stopPropagation();
    if (!onDeleteLog) return;
    setDeletingId(logId);
    try {
      await onDeleteLog(logId);
    } finally {
      setDeletingId(null);
    }
  };

  const handleCardClick = (tab?: string) => {
    if (tab && onNavigate) {
      onNavigate(tab);
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex justify-end bg-black/80 backdrop-blur-sm animate-fade-in">
      <div 
        className="fixed inset-0" 
        onClick={onClose} 
        aria-hidden="true" 
      />

      <div className="relative bg-[#0c101a] border-l border-white/10 w-full max-w-md h-full flex flex-col shadow-2xl z-10 animate-slide-left">
        {/* Panel Header */}
        <div className="px-5 py-4 border-b border-white/10 bg-[#080c14] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="relative p-2 rounded-xl bg-white text-black shadow-md">
              <Bell className="w-4 h-4 text-black" />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-blue-500 rounded-full animate-ping" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white">Notifications</h3>
                {unreadCount > 0 ? (
                  <span className="px-2 py-0.5 rounded-full bg-white text-black text-[10px] font-bold shadow-sm">
                    {unreadCount} New
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded-full bg-white/5 text-neutral-400 text-[10px] font-medium border border-white/10">
                    All caught up
                  </span>
                )}
              </div>
              <p className="text-[11px] text-neutral-400">Live alerts for PR merges, reviews & tracker events</p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={onClose}
              className="p-1.5 rounded-xl text-neutral-400 hover:text-white hover:bg-white/5 transition"
              title="Close panel"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Toolbar: Filters, Desktop Notification Permission, Mark All Read & Clear All */}
        <div className="px-5 py-2.5 border-b border-white/10 bg-[#080c14] flex items-center justify-between gap-2 text-xs">
          {/* Tab Filter */}
          <div className="flex items-center gap-1 bg-[#05080f] p-0.5 rounded-xl border border-white/10">
            <button
              onClick={() => setFilterMode('all')}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition active:scale-95 ${
                filterMode === 'all'
                  ? 'bg-white text-black font-bold shadow-sm'
                  : 'text-neutral-400 hover:text-white'
              }`}
            >
              All ({logs.length})
            </button>
            <button
              onClick={() => setFilterMode('unread')}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition active:scale-95 ${
                filterMode === 'unread'
                  ? 'bg-white text-black font-bold shadow-sm'
                  : 'text-neutral-400 hover:text-white'
              }`}
            >
              Unread ({unreadCount})
            </button>
          </div>

          {/* Right Toolbar Actions */}
          <div className="flex items-center gap-1.5">
            {/* Desktop Notification Request Button */}
            {notificationPermission !== 'granted' && typeof window !== 'undefined' && 'Notification' in window && (
              <button
                type="button"
                onClick={requestNotificationPermission}
                className="px-2 py-1 rounded-lg bg-neutral-900 text-neutral-300 border border-white/15 hover:border-white/40 hover:text-white text-[11px] font-semibold flex items-center gap-1 transition"
                title="Enable desktop notifications"
              >
                <Bell className="w-3 h-3 text-white" />
                <span className="hidden sm:inline">Allow Alerts</span>
              </button>
            )}
          </div>

          {/* Quick Actions */}
          <div className="flex items-center gap-1.5">
            {unreadCount > 0 && (
              <button
                onClick={onMarkAllRead}
                className="px-2.5 py-1 rounded-xl bg-neutral-900 hover:bg-neutral-800 text-white border border-white/20 font-medium text-[11px] transition flex items-center gap-1 active:scale-95"
                title="Mark all notifications as read"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                <span>Mark read</span>
              </button>
            )}

            {logs.length > 0 && (
              <button
                onClick={handleClearAllClick}
                disabled={isClearing}
                className="p-1.5 rounded-xl text-neutral-400 hover:text-rose-400 hover:bg-neutral-900 border border-transparent hover:border-rose-500/30 text-xs transition active:scale-95 disabled:opacity-50"
                title="Clear all notifications"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* List of recorded events */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2.5 no-scrollbar">
          {displayedLogs.length === 0 ? (
            <div className="py-24 text-center space-y-2">
              <div className="w-10 h-10 rounded-2xl bg-neutral-900 border border-white/10 flex items-center justify-center text-neutral-400 mx-auto">
                <Bell className="w-5 h-5 text-neutral-500" />
              </div>
              <p className="text-xs font-semibold text-neutral-300">
                {filterMode === 'unread' ? 'No unread notifications' : 'No notifications yet'}
              </p>
              <p className="text-[11px] text-neutral-500 max-w-xs mx-auto">
                {filterMode === 'unread' 
                  ? 'All recent platform events have been marked as read.' 
                  : 'Live updates from GitHub PRs, sync operations, and CI test runs will appear here.'}
              </p>
            </div>
          ) : (
            displayedLogs.map(log => {
              const meta = getEventMeta(log);
              const isUnread = !readLogIds.has(log.id);

              return (
                <div
                  key={log.id}
                  onClick={() => handleCardClick(meta.tab)}
                  className={`group relative rounded-2xl p-3.5 border transition-all cursor-pointer ${
                    isUnread
                      ? 'bg-[#05080f] border-white/20 hover:border-white/40 shadow-lg'
                      : 'bg-[#05080f]/60 border-white/10 hover:border-white/20'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div className="p-1.5 rounded-xl bg-neutral-900 border border-white/15 text-white">
                        {meta.icon}
                      </div>
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-1.5">
                          <h4 className="text-xs font-bold text-white group-hover:text-neutral-200 transition">
                            {meta.title}
                          </h4>
                          {isUnread && (
                            <span className="w-2 h-2 rounded-full bg-white ring-2 ring-white/20" />
                          )}
                        </div>
                        <span className="text-[10px] text-gray-500 flex items-center gap-1">
                          <Clock className="w-2.5 h-2.5" />
                          <span>{formatTimeAgo(log.created_at)}</span>
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1">
                      {onDeleteLog && (
                        <button
                          type="button"
                          onClick={(e) => handleDeleteItem(e, log.id)}
                          disabled={deletingId === log.id}
                          className="opacity-0 group-hover:opacity-100 p-1 rounded-lg text-gray-500 hover:text-rose-400 hover:bg-rose-500/10 transition"
                          title="Delete notification"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  </div>

                  <p className="mt-2 text-xs text-gray-300 leading-relaxed pl-8">
                    {meta.desc}
                  </p>

                  {meta.tab && (
                    <div className="mt-2 pl-8 flex items-center gap-1 text-[11px] text-cyan-400 group-hover:translate-x-0.5 transition-transform">
                      <span>View in {meta.tab === 'prs' ? 'Pull Requests' : meta.tab === 'issues' ? 'Issue Finder' : 'Tracker'}</span>
                      <ExternalLink className="w-3 h-3" />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Panel Footer */}
        <div className="p-3 border-t border-gray-800 bg-[#0e1424] flex items-center justify-between text-[11px] text-gray-500 px-5">
          <span>Real-time webhook & poller events</span>
          <span className="text-gray-400 font-medium">Auto-refreshed</span>
        </div>
      </div>
    </div>
  );
};

export default NotificationsPanel;
