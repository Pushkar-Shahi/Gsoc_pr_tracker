import React from 'react';
import { 
  X, Cpu, History, CreditCard, Settings, Download, 
  Sun, Moon, LogOut, Sparkles, ArrowRight, ExternalLink, User
} from 'lucide-react';
import { OrganizationSwitcher } from './OrganizationSwitcher';
import { useTheme } from '../theme';

interface MobileDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isInstallable?: boolean;
  onInstallPWA?: () => void;
  onLock?: () => void;
  onlineRunnersCount?: number;
  planTier?: string;
}

export const MobileDrawer: React.FC<MobileDrawerProps> = ({
  isOpen,
  onClose,
  activeTab,
  setActiveTab,
  isInstallable,
  onInstallPWA,
  onLock,
  onlineRunnersCount = 0,
  planTier = 'pro',
}) => {
  const { isDark, toggleTheme } = useTheme();
  const username = localStorage.getItem('issuetopr_gh_user') || 'Pushkar-Shahi';

  if (!isOpen) return null;

  const handleSelectTab = (tab: string) => {
    setActiveTab(tab);
    onClose();
  };

  const workflowItems = [
    {
      id: 'runners',
      label: 'Local Hybrid Runners',
      icon: Cpu,
      badge: onlineRunnersCount > 0 ? `${onlineRunnersCount} Online` : 'Offline',
      badgeColor: onlineRunnersCount > 0 ? 'emerald' : 'slate',
      desc: 'Offload validation runs and worktrees locally'
    },
    {
      id: 'history',
      label: 'Activity Timeline & Audit',
      icon: History,
      desc: 'Chronological triage and PR event logs'
    },
  ];

  const profileItems = [
    {
      id: 'settings',
      label: 'Platform Settings',
      icon: Settings,
      desc: 'AI tokens, GitHub sync, and triage policies'
    },
    {
      id: 'billing',
      label: 'Billing & Early Adopter Perks',
      icon: CreditCard,
      badge: '100% FREE',
      badgeColor: 'blue',
      desc: 'Founder Beta tier and feature entitlements'
    },
  ];

  const renderNavCard = (item: any) => {
    const Icon = item.icon;
    const isActive = activeTab === item.id;
    return (
      <button
        key={item.id}
        onClick={() => handleSelectTab(item.id)}
        className={`w-full flex items-center justify-between p-3 rounded-xl text-left transition active:scale-95 ${
          isActive
            ? 'bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/40 dark:text-white dark:border-blue-500/30 font-bold'
            : 'text-slate-700 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-300 dark:hover:text-white dark:hover:bg-white/5 border border-transparent'
        }`}
      >
        <div className="flex items-start gap-3">
          <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${
            isActive ? 'text-blue-700 dark:text-blue-400' : 'text-slate-500 dark:text-neutral-400'
          }`} />
          <div>
            <div className="text-xs font-semibold">{item.label}</div>
            <div className="text-[10px] text-slate-500 dark:text-neutral-400">{item.desc}</div>
          </div>
        </div>

        {item.badge && (
          <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full shrink-0 ${
            item.badgeColor === 'emerald'
              ? 'bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20'
              : item.badgeColor === 'blue'
              ? 'bg-blue-100 text-blue-800 border border-blue-300 dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-400/30'
              : 'bg-slate-100 text-slate-600 dark:bg-neutral-800 dark:text-neutral-300'
          }`}>
            {item.badge}
          </span>
        )}
      </button>
    );
  };

  return (
    <div className="fixed inset-0 z-50 md:hidden animate-fade-in">
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/60 dark:bg-black/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Slide-over panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-xs bg-white dark:bg-[#080c14] border-l border-slate-200 dark:border-white/10 shadow-2xl flex flex-col z-50 p-4 sm:p-5 overflow-y-auto">
        {/* Header with Quick Theme Toggle and Close */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-white/10 shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-900 dark:text-white font-mono">
              Workspace & Menu
            </span>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200 dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-400/30 font-mono">
              {planTier.toUpperCase()}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={toggleTheme}
              className="w-8 h-8 rounded-xl flex items-center justify-center text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/10 transition active:scale-95"
              title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
              aria-label="Toggle theme"
            >
              {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-700" />}
            </button>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/10 transition active:scale-95"
              aria-label="Close menu"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Workspace Switcher in Drawer */}
        <div className="py-2.5 border-b border-slate-100 dark:border-white/5 shrink-0">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 dark:text-neutral-500 font-semibold">
              Active Workspace
            </span>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-neutral-300 font-medium">
              <User className="w-3.5 h-3.5 text-blue-500" />
              <span className="truncate max-w-[120px]">{username}</span>
            </div>
          </div>
          <OrganizationSwitcher />
        </div>

        {/* Quick Actions (Appearance, Star on GitHub, Sign Out) - Put right here near the top! */}
        <div className="py-2.5 border-b border-slate-100 dark:border-white/5 space-y-1.5 shrink-0">
          <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 dark:text-neutral-500 block font-semibold">
            Quick Actions
          </span>
          <div className="grid grid-cols-2 gap-1.5">
            {/* Appearance Toggle Button */}
            <button
              type="button"
              onClick={toggleTheme}
              className="flex items-center justify-between p-2 rounded-xl bg-slate-50 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 border border-slate-200 dark:border-white/10 text-xs font-semibold text-slate-800 dark:text-neutral-200 transition active:scale-95"
              title="Toggle Light / Dark mode"
            >
              <div className="flex items-center gap-1.5 min-w-0">
                {isDark ? <Sun className="w-3.5 h-3.5 text-amber-400 shrink-0" /> : <Moon className="w-3.5 h-3.5 text-slate-700 shrink-0" />}
                <span className="truncate text-[11px]">Theme</span>
              </div>
              <span className="text-[9px] font-mono font-bold text-slate-500 dark:text-neutral-400 uppercase">
                {isDark ? 'Dark' : 'Light'}
              </span>
            </button>

            {/* Star on GitHub */}
            <a
              href="https://github.com/Pushkar-Shahi/Issue-2-PR"
              target="_blank"
              rel="noreferrer"
              className="flex items-center justify-between p-2 rounded-xl bg-slate-50 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 border border-slate-200 dark:border-white/10 text-xs font-semibold text-slate-800 dark:text-neutral-200 transition active:scale-95"
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <Sparkles className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                <span className="truncate text-[11px]">GitHub</span>
              </div>
              <ExternalLink className="w-3 h-3 text-slate-400 dark:text-neutral-500 shrink-0" />
            </a>
          </div>

          {/* Sign Out Button */}
          {onLock && (
            <button
              type="button"
              onClick={() => {
                onClose();
                onLock();
              }}
              className="w-full flex items-center justify-center gap-2 py-1.5 px-3 rounded-xl text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:text-rose-400 dark:hover:text-rose-300 dark:hover:bg-rose-950/30 border border-rose-200/60 dark:border-rose-500/20 text-xs font-semibold transition active:scale-95"
            >
              <LogOut className="w-3.5 h-3.5 shrink-0" />
              <span>Sign Out of Platform</span>
            </button>
          )}
        </div>

        {/* Profile & Account Views */}
        <div className="space-y-1.5 py-2.5 border-b border-slate-100 dark:border-white/5 shrink-0">
          <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 dark:text-neutral-500 block font-semibold">
            Profile & Account
          </span>
          {profileItems.map(renderNavCard)}
        </div>

        {/* Workflow & Fleet Views */}
        <div className="space-y-1.5 py-2.5 shrink-0">
          <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 dark:text-neutral-500 block font-semibold">
            Workflow & Fleet
          </span>
          {workflowItems.map(renderNavCard)}
        </div>

        {/* PWA Install Promotion Banner (if installable) */}
        {isInstallable && onInstallPWA && (
          <div className="mt-2.5 p-2.5 rounded-xl bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-500/30 flex items-center justify-between gap-2 shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <Download className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />
              <div className="min-w-0">
                <div className="text-[11px] font-bold text-slate-900 dark:text-white truncate">Install Mobile App</div>
                <div className="text-[9px] text-slate-500 dark:text-neutral-400 truncate">Offline & home screen access</div>
              </div>
            </div>
            <button
              onClick={() => {
                onInstallPWA();
                onClose();
              }}
              className="px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold text-[10px] shrink-0 active:scale-95 transition"
            >
              Install
            </button>
          </div>
        )}

        <div className="text-center pt-3 pb-2 shrink-0">
          <span className="text-[10px] font-mono text-slate-400 dark:text-neutral-600">
            Issue-to-PR v1.0.0 • PWA Ready
          </span>
        </div>
      </div>
    </div>
  );
};
