import React from 'react';
import { 
  Sparkles, RefreshCw, ShieldCheck, Database, 
  Terminal, CheckCircle2, AlertTriangle, ExternalLink,
  Lock, Download, Sun, Moon
} from 'lucide-react';
import { DiscoveryStatus, PlatformSettings } from '../types';
import { OrganizationSwitcher } from './OrganizationSwitcher';
import { useTheme } from '../theme';
import { BrandIcon } from './BrandIcon';

interface HeaderProps {
  discoveryStatus: DiscoveryStatus | null;
  settings: PlatformSettings | null;
  onRefreshDiscovery: () => void;
  isSyncing: boolean;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  onLock?: () => void;
  isInstallable?: boolean;
  onInstallPWA?: () => void;
  planTier?: string;
}

export const Header: React.FC<HeaderProps> = ({
  discoveryStatus,
  settings,
  onRefreshDiscovery,
  isSyncing,
  activeTab,
  setActiveTab,
  onLock,
  isInstallable,
  onInstallPWA,
  planTier = 'starter'
}) => {
  const { isDark, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-40 liquid-glass-header">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo, Platform Name & Organization Switcher */}
          <div className="flex items-center gap-3">
            <BrandIcon size={38} className="shadow-lg shadow-emerald-500/20 shrink-0 rounded-2xl active:scale-95 transition-transform cursor-pointer" />
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm sm:text-base tracking-tight whitespace-nowrap bg-clip-text text-transparent bg-gradient-to-r from-slate-900 via-slate-700 to-slate-900 dark:from-white dark:via-neutral-100 dark:to-neutral-400">
                  Issue-to-PR
                </span>
                <span className="hidden sm:inline-flex text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 border border-indigo-200 dark:bg-indigo-950/80 dark:text-indigo-300 dark:border-indigo-500/30 font-mono shadow-sm">
                  GSoC Fleet
                </span>
              </div>
              <p className="text-[10px] text-slate-500 dark:text-neutral-400 hidden sm:block font-mono">
                Multi-Tenant Autonomous Pipeline
              </p>
            </div>

            {/* Organization Workspace Switcher */}
            <div className="ml-1 sm:ml-3 pl-2 sm:pl-3 border-l border-slate-200 dark:border-white/10">
              <OrganizationSwitcher />
            </div>
          </div>

          {/* System Status Badges (Laptops / Desktops) */}
          <div className="hidden lg:flex items-center gap-2.5 text-xs">
            {/* DB Status Badge */}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-cyan-50 border border-cyan-200 text-cyan-700 dark:bg-cyan-950/20 dark:border-cyan-500/20 dark:text-cyan-300 shadow-sm backdrop-blur-xl">
              <Database className="w-3.5 h-3.5 text-cyan-500 dark:text-cyan-400" />
              <span className="font-medium text-[11px]">Storage: PostgreSQL</span>
            </div>

            {/* Plan Tier Badge */}
            <button
              onClick={() => setActiveTab('billing')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition active:scale-95 shadow-sm backdrop-blur-xl ${
                planTier === 'pro'
                  ? 'bg-gradient-to-r from-indigo-950/80 to-purple-950/80 border-indigo-500/40 text-indigo-300 hover:border-indigo-400'
                  : planTier === 'team'
                  ? 'bg-gradient-to-r from-emerald-950/80 to-teal-950/80 border-emerald-500/40 text-emerald-300 hover:border-emerald-400'
                  : 'bg-slate-100 border-slate-200 text-slate-700 hover:border-slate-300 dark:bg-neutral-900/60 dark:border-white/10 dark:text-neutral-300 dark:hover:border-white/25'
              }`}
              title="View subscription and plan limits"
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400" />
              <span className="capitalize">{planTier} Plan</span>
            </button>

            {/* GitHub Token Status */}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 dark:bg-emerald-950/20 dark:border-emerald-500/20 dark:text-emerald-300 shadow-sm backdrop-blur-xl">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              <span className="font-medium text-[11px]">
                GitHub API: {settings?.github_token_configured ? 'Authenticated (5k/hr)' : 'Public (60/hr)'}
              </span>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1.5 sm:gap-2">
            {/* Install PWA Button (when installable) */}
            {isInstallable && onInstallPWA && (
              <button
                onClick={onInstallPWA}
                className="flex items-center gap-1.5 h-9 px-3 rounded-xl text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300 hover:bg-slate-200 hover:text-slate-900 dark:bg-neutral-900/80 dark:text-neutral-200 dark:border-white/15 dark:hover:bg-neutral-800 dark:hover:text-white active:scale-95 transition backdrop-blur-xl"
                title="Install PWA on your device"
              >
                <Download className="w-3.5 h-3.5 text-cyan-500 dark:text-cyan-400" />
                <span className="hidden md:inline">Install App</span>
              </button>
            )}

            {/* Light / Dark Mode Toggle Button */}
            <button
              onClick={toggleTheme}
              className="h-9 w-9 rounded-xl bg-slate-100 dark:bg-neutral-900/80 border border-slate-300 dark:border-white/15 text-slate-700 dark:text-neutral-300 hover:text-amber-500 dark:hover:text-amber-400 hover:border-amber-400/50 dark:hover:border-amber-400/50 transition flex items-center justify-center active:scale-95 shadow-sm backdrop-blur-xl"
              title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
              aria-label="Toggle color theme"
            >
              {isDark ? (
                <Sun className="w-4 h-4 text-amber-400 transition-transform hover:rotate-45" />
              ) : (
                <Moon className="w-4 h-4 text-indigo-600 transition-transform hover:-rotate-12" />
              )}
            </button>

            {/* Trigger Sync Button */}
            <button
              onClick={onRefreshDiscovery}
              disabled={isSyncing}
              className={`flex items-center gap-2 h-9 px-3 sm:px-3.5 rounded-xl text-xs font-semibold border transition-all active:scale-95 shadow-md ${
                isSyncing
                  ? 'bg-slate-200 text-slate-400 border-slate-300 dark:bg-neutral-900/80 dark:text-neutral-500 dark:border-white/10 cursor-not-allowed'
                  : 'bg-gradient-to-r from-indigo-500 to-cyan-500 hover:from-indigo-400 hover:to-cyan-400 text-white border-transparent shadow-indigo-500/25'
              }`}
              title="Sync live status for all tracked PRs and issues"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">{isSyncing ? 'Syncing...' : 'Sync Live'}</span>
            </button>

            {/* Lock Button */}
            {onLock && (
              <button
                onClick={onLock}
                className="h-9 w-9 rounded-xl bg-slate-100 dark:bg-neutral-900/80 border border-slate-300 dark:border-white/15 text-slate-600 dark:text-neutral-400 hover:text-slate-900 dark:hover:text-white hover:border-slate-400 dark:hover:border-white/40 hover:bg-slate-200 dark:hover:bg-neutral-800 transition flex items-center justify-center active:scale-95 shadow-sm backdrop-blur-xl"
                title="Lock platform"
              >
                <Lock className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};
