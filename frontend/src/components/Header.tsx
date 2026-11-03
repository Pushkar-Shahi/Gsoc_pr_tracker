import React from 'react';
import { 
  Sparkles, RefreshCw, ShieldCheck, Database, 
  Terminal, CheckCircle2, AlertTriangle, ExternalLink,
  Lock, Download
} from 'lucide-react';
import { DiscoveryStatus, PlatformSettings } from '../types';

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
    <header className="sticky top-0 z-40 bg-[#000000]/90 backdrop-blur-xl border-b border-white/10">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo and Platform Name */}
          <div className="flex items-center gap-2.5 sm:gap-3">
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-white text-black flex items-center justify-center shadow-lg shadow-white/10 shrink-0">
              <Sparkles className="w-5 h-5 text-black" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm sm:text-lg tracking-tight text-white whitespace-nowrap">Contribution & PR Tracker</span>
                <span className="hidden sm:inline-flex text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-neutral-900 text-neutral-300 border border-white/20">
                  Live GitHub Monitor
                </span>
              </div>
              <p className="text-[11px] text-neutral-400 hidden sm:block">
                Real-time Live Tracking for Pull Requests, CI Checks & Active Issues
              </p>
            </div>
          </div>

          {/* System Status Badges (Laptops / Desktops) */}
          <div className="hidden lg:flex items-center gap-3 text-xs">
            {/* DB Status */}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#080808] border border-white/10 text-neutral-300">
              <Database className="w-3.5 h-3.5 text-white" />
              <span>Storage: Connected</span>
            </div>

            {/* Plan Tier Badge */}
            <button
              onClick={() => setActiveTab('billing')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition active:scale-95 ${
                planTier === 'pro'
                  ? 'bg-indigo-500/10 border-indigo-500/30 text-indigo-300 hover:bg-indigo-500/20'
                  : planTier === 'team'
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/20'
                  : 'bg-[#080808] border-white/10 text-neutral-300 hover:border-white/20'
              }`}
              title="View subscription and plan limits"
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              <span className="capitalize">{planTier} Plan</span>
            </button>

            {/* GitHub Token Status */}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#080808] border border-white/10 text-neutral-300">
              <ShieldCheck className="w-3.5 h-3.5 text-white" />
              <span>
                GitHub API: {settings?.github_token_configured ? 'Authenticated (5,000/hr)' : 'Public (60/hr)'}
              </span>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1.5 sm:gap-2">
            {/* Install PWA Button (when installable) */}
            {isInstallable && onInstallPWA && (
              <button
                onClick={onInstallPWA}
                className="flex items-center gap-1.5 h-9 px-3 rounded-xl text-xs font-semibold bg-neutral-900 text-neutral-200 border border-white/20 hover:bg-neutral-800 hover:text-white active:scale-95 transition"
                title="Install PWA on your device"
              >
                <Download className="w-3.5 h-3.5" />
                <span className="hidden md:inline">Install App</span>
              </button>
            )}

            {/* Trigger Sync Button */}
            <button
              onClick={onRefreshDiscovery}
              disabled={isSyncing}
              className={`flex items-center gap-2 h-9 px-3 sm:px-3.5 rounded-xl text-xs font-semibold border transition-all active:scale-95 ${
                isSyncing
                  ? 'bg-neutral-900 text-neutral-500 border-white/10 cursor-not-allowed'
                  : 'bg-white text-black hover:bg-neutral-200 border-white shadow-sm'
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
                className="h-9 w-9 rounded-xl bg-[#080808] border border-white/15 text-neutral-400 hover:text-white hover:border-white/40 hover:bg-neutral-900 transition flex items-center justify-center active:scale-95 shadow-sm"
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

