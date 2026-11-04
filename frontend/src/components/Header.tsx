import React from 'react';
import { 
  Sparkles, RefreshCw, ShieldCheck, Database, 
  Terminal, CheckCircle2, AlertTriangle, ExternalLink,
  Lock, Download
} from 'lucide-react';
import { DiscoveryStatus, PlatformSettings } from '../types';
import { OrganizationSwitcher } from './OrganizationSwitcher';

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
  return (
    <header className="sticky top-0 z-40 liquid-glass-header">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo, Platform Name & Organization Switcher */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-cyan-500 p-0.5 shadow-lg shadow-indigo-500/20 shrink-0">
              <div className="w-full h-full bg-[#08080d] rounded-[10px] flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-cyan-300 animate-pulse" />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm sm:text-base tracking-tight text-white whitespace-nowrap bg-clip-text text-transparent bg-gradient-to-r from-white via-neutral-100 to-neutral-400">
                  Issue-to-PR
                </span>
                <span className="hidden sm:inline-flex text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-indigo-950/80 text-indigo-300 border border-indigo-500/30 font-mono shadow-sm">
                  GSoC Fleet
                </span>
              </div>
              <p className="text-[10px] text-neutral-400 hidden sm:block font-mono">
                Multi-Tenant Autonomous Pipeline
              </p>
            </div>

            {/* Organization Workspace Switcher */}
            <div className="ml-1 sm:ml-3 pl-2 sm:pl-3 border-l border-white/10">
              <OrganizationSwitcher />
            </div>
          </div>

          {/* System Status Badges (Laptops / Desktops) */}
          <div className="hidden lg:flex items-center gap-2.5 text-xs">
            {/* DB Status Badge */}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-cyan-950/20 border border-cyan-500/20 text-cyan-300 shadow-sm backdrop-blur-xl">
              <Database className="w-3.5 h-3.5 text-cyan-400" />
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
                  : 'bg-neutral-900/60 border-white/10 text-neutral-300 hover:border-white/25'
              }`}
              title="View subscription and plan limits"
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              <span className="capitalize">{planTier} Plan</span>
            </button>

            {/* GitHub Token Status */}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-950/20 border border-emerald-500/20 text-emerald-300 shadow-sm backdrop-blur-xl">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
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
                className="flex items-center gap-1.5 h-9 px-3 rounded-xl text-xs font-semibold bg-neutral-900/80 text-neutral-200 border border-white/15 hover:bg-neutral-800 hover:text-white active:scale-95 transition backdrop-blur-xl"
                title="Install PWA on your device"
              >
                <Download className="w-3.5 h-3.5 text-cyan-400" />
                <span className="hidden md:inline">Install App</span>
              </button>
            )}

            {/* Trigger Sync Button */}
            <button
              onClick={onRefreshDiscovery}
              disabled={isSyncing}
              className={`flex items-center gap-2 h-9 px-3 sm:px-3.5 rounded-xl text-xs font-semibold border transition-all active:scale-95 shadow-md ${
                isSyncing
                  ? 'bg-neutral-900/80 text-neutral-500 border-white/10 cursor-not-allowed'
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
                className="h-9 w-9 rounded-xl bg-neutral-900/80 border border-white/15 text-neutral-400 hover:text-white hover:border-white/40 hover:bg-neutral-800 transition flex items-center justify-center active:scale-95 shadow-sm backdrop-blur-xl"
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
