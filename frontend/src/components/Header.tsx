import React from 'react';
import { Sun, Moon, User as UserIcon } from 'lucide-react';
import { DiscoveryStatus, PlatformSettings } from '../types';
import { OrganizationSwitcher } from './OrganizationSwitcher';
import { useTheme } from '../theme';

interface HeaderProps {
  discoveryStatus?: DiscoveryStatus | null;
  settings?: PlatformSettings | null;
  onRefreshDiscovery: () => void;
  isSyncing: boolean;
  activeTab?: string;
  setActiveTab?: (tab: string) => void;
  onLock?: () => void;
  isInstallable?: boolean;
  onInstallPWA?: () => void;
  planTier?: string;
}

export const Header: React.FC<HeaderProps> = ({
  onRefreshDiscovery,
  isSyncing,
  onLock,
  setActiveTab
}) => {
  const { isDark, toggleTheme } = useTheme();

  return (
    <header className="h-16 px-6 sm:px-8 flex items-center justify-between border-b border-white/5 bg-[#080c14]/80 backdrop-blur-md sticky top-0 z-20">
      {/* Left: Organization / Account Switcher */}
      <div className="flex items-center gap-3">
        <OrganizationSwitcher />
      </div>

      {/* Right Controls: Theme Toggle, Sync Live, Profile */}
      <div className="flex items-center gap-3">
        {/* Theme Toggle Button */}
        <button
          onClick={toggleTheme}
          className="w-9 h-9 rounded-xl flex items-center justify-center text-neutral-400 hover:text-white hover:bg-white/5 transition active:scale-95"
          title="Toggle light / dark mode"
        >
          {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Sync Live Button */}
        <button
          onClick={onRefreshDiscovery}
          disabled={isSyncing}
          className="px-3.5 py-1.5 rounded-full bg-white/5 hover:bg-white/10 border border-white/10 text-white text-xs font-semibold flex items-center gap-2 transition active:scale-95 disabled:opacity-50"
          title="Sync live status and issues with GitHub"
        >
          <span className={`w-2 h-2 rounded-full bg-emerald-400 ${isSyncing ? 'animate-ping' : ''}`} />
          <span>{isSyncing ? 'Syncing...' : 'Sync Live'}</span>
        </button>

        {/* User Profile / Settings */}
        <button
          onClick={() => setActiveTab ? setActiveTab('settings') : onLock?.()}
          className="w-8 h-8 rounded-full bg-neutral-800 border border-white/10 flex items-center justify-center text-neutral-300 hover:text-white hover:border-white/20 transition active:scale-95"
          title="Open Settings & Account"
        >
          <UserIcon className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
