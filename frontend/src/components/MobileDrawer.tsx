import React from 'react';
import { 
  X, Cpu, History, CreditCard, Settings, Download, 
  Sun, Moon, LogOut, Sparkles, ArrowRight, ExternalLink
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

  if (!isOpen) return null;

  const handleSelectTab = (tab: string) => {
    setActiveTab(tab);
    onClose();
  };

  const menuItems = [
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
    {
      id: 'billing',
      label: 'Billing & Early Adopter Perks',
      icon: CreditCard,
      badge: '100% FREE',
      badgeColor: 'blue',
      desc: 'Founder Beta tier and feature entitlements'
    },
    {
      id: 'settings',
      label: 'Platform Settings',
      icon: Settings,
      desc: 'AI tokens, GitHub sync, and triage policies'
    },
  ];

  return (
    <div className="fixed inset-0 z-50 md:hidden animate-fade-in">
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/60 dark:bg-black/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Slide-over panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-xs bg-white dark:bg-[#080c14] border-l border-slate-200 dark:border-white/10 shadow-2xl flex flex-col z-50 p-5 overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-white/10">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-900 dark:text-white font-mono">
              Workspace & Menu
            </span>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200 dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-400/30 font-mono">
              {planTier.toUpperCase()}
            </span>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/10 transition active:scale-95"
            aria-label="Close menu"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Workspace Switcher in Drawer */}
        <div className="py-4 border-b border-slate-100 dark:border-white/5">
          <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 dark:text-neutral-500 mb-2 block font-semibold">
            Active Workspace
          </span>
          <OrganizationSwitcher />
        </div>

        {/* PWA Install Promotion Card (if installable or on mobile) */}
        {isInstallable && onInstallPWA && (
          <div className="my-4 p-3.5 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-600/20 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Download className="w-4 h-4 text-white" />
                <span className="text-xs font-bold">Install Mobile App</span>
              </div>
              <span className="text-[9px] font-mono font-bold bg-white/20 px-1.5 py-0.2 rounded-full">
                PWA
              </span>
            </div>
            <p className="text-[11px] text-blue-100 leading-relaxed">
              Add IssueToPR to your home screen for full-screen launches and offline access.
            </p>
            <button
              onClick={() => {
                onInstallPWA();
                onClose();
              }}
              className="w-full mt-1 py-2 px-3 rounded-xl bg-white text-blue-700 font-bold text-xs flex items-center justify-center gap-1.5 hover:bg-blue-50 active:scale-95 transition shadow-sm"
            >
              <span>Install to Device</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Navigation Items */}
        <div className="space-y-1.5 py-3">
          <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400 dark:text-neutral-500 mb-1 block font-semibold">
            More Views
          </span>
          {menuItems.map((item) => {
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
          })}
        </div>

        {/* Footer Actions */}
        <div className="mt-auto pt-4 border-t border-slate-200 dark:border-white/10 space-y-2">
          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            className="w-full flex items-center justify-between p-3 rounded-xl bg-slate-50 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 border border-slate-200 dark:border-white/10 text-xs font-medium text-slate-800 dark:text-neutral-200 transition"
          >
            <div className="flex items-center gap-2.5">
              {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-700" />}
              <span>Appearance</span>
            </div>
            <span className="text-[11px] font-mono text-slate-500 dark:text-neutral-400 uppercase font-semibold">
              {isDark ? 'Dark Mode' : 'Light Mode'}
            </span>
          </button>

          {/* GitHub Repository Link */}
          <a
            href="https://github.com/Pushkar-Shahi/Issue-2-PR"
            target="_blank"
            rel="noreferrer"
            className="w-full flex items-center justify-between p-3 rounded-xl bg-slate-50 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 border border-slate-200 dark:border-white/10 text-xs font-medium text-slate-800 dark:text-neutral-200 transition"
          >
            <div className="flex items-center gap-2.5">
              <Sparkles className="w-4 h-4 text-amber-500" />
              <span>Star on GitHub</span>
            </div>
            <ExternalLink className="w-3.5 h-3.5 text-slate-400 dark:text-neutral-500" />
          </a>

          {/* Sign Out */}
          {onLock && (
            <button
              onClick={() => {
                onClose();
                onLock();
              }}
              className="w-full flex items-center gap-2.5 p-3 rounded-xl text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:text-rose-400 dark:hover:text-rose-300 dark:hover:bg-rose-950/40 text-xs font-medium transition"
            >
              <LogOut className="w-4 h-4" />
              <span>Sign Out of Platform</span>
            </button>
          )}

          <div className="text-center pt-2">
            <span className="text-[10px] font-mono text-slate-400 dark:text-neutral-600">
              Issue-to-PR v1.0.0 • PWA Ready
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
