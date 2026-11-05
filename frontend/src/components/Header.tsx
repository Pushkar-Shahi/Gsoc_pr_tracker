import React, { useState, useRef, useEffect } from 'react';
import { Sun, Moon, User as UserIcon, Settings, CreditCard, LogOut } from 'lucide-react';
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
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    };
    if (isMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isMenuOpen]);

  const username = localStorage.getItem('issuetopr_gh_user') || 'Pushkar-Shahi';

  const handleOpenTab = (tab: string) => {
    if (setActiveTab) {
      setActiveTab(tab);
    }
    setIsMenuOpen(false);
  };

  const handleExplicitLogout = () => {
    setIsMenuOpen(false);
    if (window.confirm('Are you sure you want to sign out of Issue-to-PR?')) {
      if (onLock) {
        onLock();
      }
    }
  };

  return (
    <header className="h-16 px-6 sm:px-8 flex items-center justify-between border-b border-slate-200 dark:border-white/5 bg-white/85 dark:bg-[#080c14]/80 backdrop-blur-md sticky top-0 z-20">
      {/* Left: Organization / Account Switcher & Early Access Badge */}
      <div className="flex items-center gap-2.5">
        <OrganizationSwitcher />
        <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-500/30 text-[11px] font-semibold select-none shadow-xs">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-600 dark:bg-blue-400 animate-pulse" />
          <span>Early Access Beta</span>
        </div>
      </div>

      {/* Right Controls: Theme Toggle, Sync Live, Profile */}
      <div className="flex items-center gap-3">
        {/* Theme Toggle Button */}
        <button
          onClick={toggleTheme}
          className="w-9 h-9 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/5 transition active:scale-95"
          title="Toggle light / dark mode"
        >
          {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-700" />}
        </button>

        {/* Sync Live Button */}
        <button
          onClick={onRefreshDiscovery}
          disabled={isSyncing}
          className="px-3.5 py-1.5 rounded-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-800 dark:bg-white/5 dark:hover:bg-white/10 dark:border-white/10 dark:text-white text-xs font-semibold flex items-center gap-2 transition active:scale-95 disabled:opacity-50"
          title="Sync live status and issues with GitHub"
        >
          <span className={`w-2 h-2 rounded-full bg-emerald-500 ${isSyncing ? 'animate-ping' : ''}`} />
          <span>{isSyncing ? 'Syncing...' : 'Sync Live'}</span>
        </button>

        {/* User Profile Dropdown Menu (Safe, never logs out on click) */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setIsMenuOpen(prev => !prev)}
            className="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 dark:bg-neutral-800 dark:hover:bg-neutral-700 dark:border-white/10 dark:text-neutral-300 hover:text-slate-900 dark:hover:text-white transition active:scale-95 shadow-sm flex items-center justify-center"
            title="Account & Settings menu"
          >
            <UserIcon className="w-4 h-4" />
          </button>

          {isMenuOpen && (
            <div className="absolute right-0 mt-2 w-56 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/15 p-2 shadow-2xl z-50 animate-fade-in space-y-1">
              {/* User Header */}
              <div className="px-3 py-2.5 border-b border-slate-100 dark:border-white/10 mb-1">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-blue-50 dark:bg-blue-600/20 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/30 flex items-center justify-center font-bold text-xs uppercase">
                    {username.charAt(0)}
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="text-xs font-bold text-slate-900 dark:text-white truncate">{username}</span>
                    <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">● Active Session</span>
                  </div>
                </div>
              </div>

              {/* Navigation Actions */}
              <button
                type="button"
                onClick={() => handleOpenTab('settings')}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-700 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-300 dark:hover:text-white dark:hover:bg-white/10 rounded-xl transition font-medium text-left"
              >
                <Settings className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                <span>Platform Settings</span>
              </button>

              <button
                type="button"
                onClick={() => handleOpenTab('billing')}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-700 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-300 dark:hover:text-white dark:hover:bg-white/10 rounded-xl transition font-medium text-left"
              >
                <CreditCard className="w-4 h-4 text-rose-500 dark:text-rose-400" />
                <span>Billing & Plans</span>
              </button>

              {/* Divider */}
              <div className="h-px bg-slate-100 dark:bg-white/10 my-1" />

              {/* Sign Out Option */}
              <button
                type="button"
                onClick={handleExplicitLogout}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:text-rose-400 dark:hover:text-rose-300 dark:hover:bg-rose-950/40 rounded-xl transition font-medium text-left"
              >
                <LogOut className="w-4 h-4" />
                <span>Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
