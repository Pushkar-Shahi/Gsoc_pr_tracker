import React, { useState, useRef, useEffect } from 'react';
import { Sun, Moon, User as UserIcon, Settings, CreditCard, LogOut, Download, Menu, Heart, ShieldCheck } from 'lucide-react';
import { DiscoveryStatus, PlatformSettings, SubscriptionInfo } from '../types';
import { OrganizationSwitcher } from './OrganizationSwitcher';
import { useTheme } from '../theme';
import { useLockBodyScroll } from '../hooks/useLockBodyScroll';
import { logout } from '../api';

interface HeaderProps {
  discoveryStatus?: DiscoveryStatus | null;
  settings?: PlatformSettings | null;
  onRefreshDiscovery: () => void;
  isSyncing: boolean;
  activeTab?: string;
  setActiveTab?: (tab: string) => void;
  onLock?: () => void;
  onOpenSupportUpi?: () => void;
  onOpenTeamSettings?: () => void;
  isInstallable?: boolean;
  onInstallPWA?: () => void;
  onToggleMobileMenu?: () => void;
  planTier?: string;
  subscriptionInfo?: SubscriptionInfo | null;
}

export const Header: React.FC<HeaderProps> = ({
  onRefreshDiscovery,
  isSyncing,
  onLock,
  onOpenSupportUpi,
  onOpenTeamSettings,
  activeTab,
  setActiveTab,
  isInstallable,
  onInstallPWA,
  onToggleMobileMenu,
  planTier = 'pro',
  subscriptionInfo,
}) => {
  const { isDark, toggleTheme } = useTheme();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Lock scrolling when Profile Menu is open
  useLockBodyScroll(isMenuOpen);

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
    if (onLock) {
      onLock();
    } else {
      logout();
    }
  };

  return (
    <header className="h-16 px-3.5 sm:px-8 flex items-center justify-between border-b border-slate-200 dark:border-white/5 bg-white/92 dark:bg-[#080c14]/90 backdrop-blur-sm sticky top-0 z-20 transform-gpu">
      {/* Left: Organization / Account Switcher & Active Tier / Trial Badge */}
      <div className="flex items-center gap-2 sm:gap-2.5 min-w-0">
        <OrganizationSwitcher onOpenTeamSettings={onOpenTeamSettings} />
        {(() => {
          const effectiveTier = subscriptionInfo?.tier || planTier || 'pro';
          const trialActive = Boolean(subscriptionInfo?.trial_active);
          const daysLeft = subscriptionInfo?.trial_days_remaining ?? 15;
          const isUrgent = trialActive && daysLeft <= 3;

          let label = 'Early Access Beta';
          let pillClasses = 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-500/30';
          let dotClasses = 'bg-blue-600 dark:bg-blue-400';

          if (!subscriptionInfo?.free_beta_mode) {
            if (trialActive) {
              label = `Pro Trial • ${daysLeft}d left`;
              if (isUrgent) {
                pillClasses = 'bg-amber-50 text-amber-800 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/40';
                dotClasses = 'bg-amber-500 animate-ping';
              } else {
                pillClasses = 'bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/50 dark:text-indigo-300 dark:border-indigo-500/30';
                dotClasses = 'bg-indigo-500 animate-pulse';
              }
            } else if (subscriptionInfo?.trial_expired && effectiveTier === 'starter') {
              label = 'Starter • Trial Ended';
              pillClasses = 'bg-slate-100 text-slate-700 border-slate-300 dark:bg-white/5 dark:text-neutral-300 dark:border-white/15';
              dotClasses = 'bg-amber-500';
            } else if (effectiveTier === 'team') {
              label = 'Engineering Team';
              pillClasses = 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-500/30';
              dotClasses = 'bg-emerald-500';
            } else if (effectiveTier === 'pro') {
              label = 'Pro Developer';
            } else {
              label = 'Starter Free';
              pillClasses = 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-white/5 dark:text-neutral-300 dark:border-white/10';
              dotClasses = 'bg-slate-400';
            }
          }

          return (
            <button
              type="button"
              onClick={() => setActiveTab?.('billing')}
              title="View plan details, 15-day trial status, and UPI upgrades"
              className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-semibold select-none shadow-xs shrink-0 transition hover:opacity-90 active:scale-95 ${pillClasses}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${dotClasses}`} />
              <span>{label}</span>
            </button>
          );
        })()}
      </div>

      {/* Right Controls: Install App, Theme Toggle, Sync Live, Profile, Mobile Menu */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Install PWA Button (Visible when installable) */}
        {isInstallable && onInstallPWA && (
          <button
            onClick={onInstallPWA}
            className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-sm shadow-blue-600/20 active:scale-95 transition"
            title="Install Issue-to-PR PWA App"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Install App</span>
          </button>
        )}

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
          className="hidden xs:flex px-3 sm:px-3.5 py-1.5 rounded-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-800 dark:bg-white/5 dark:hover:bg-white/10 dark:border-white/10 dark:text-white text-xs font-semibold items-center gap-1.5 sm:gap-2 transition active:scale-95 disabled:opacity-50"
          title="Sync live status and issues with GitHub"
        >
          <span className={`w-2 h-2 rounded-full bg-emerald-500 ${isSyncing ? 'animate-ping' : ''}`} />
          <span className="hidden sm:inline">{isSyncing ? 'Syncing...' : 'Sync Live'}</span>
          <span className="sm:hidden">{isSyncing ? '...' : 'Sync'}</span>
        </button>

        {/* User Profile Dropdown Menu (Safe, never logs out on click) */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setIsMenuOpen(prev => !prev)}
            className={`w-8 h-8 rounded-full border transition active:scale-95 shadow-sm flex items-center justify-center ${
              activeTab === 'settings' || activeTab === 'billing'
                ? 'bg-blue-50 border-blue-400 text-blue-600 dark:bg-blue-600/20 dark:border-blue-500/50 dark:text-blue-400 ring-2 ring-blue-500/30'
                : 'bg-slate-100 hover:bg-slate-200 border-slate-200 text-slate-700 dark:bg-neutral-800 dark:hover:bg-neutral-700 dark:border-white/10 dark:text-neutral-300 hover:text-slate-900 dark:hover:text-white'
            }`}
            title="Account & Profile (Settings, Billing, Logout)"
          >
            <UserIcon className="w-4 h-4" />
          </button>

          {isMenuOpen && (
            <>
              {/* Mobile Backdrop: Locks touches and closes on background tap */}
              <div 
                className="fixed inset-0 z-40 bg-black/40 backdrop-blur-xs md:hidden"
                onClick={() => setIsMenuOpen(false)}
              />
              <div className="absolute right-0 mt-2 w-64 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/15 p-2 shadow-2xl z-50 animate-dropdown space-y-1">
              {/* User Header */}
              <div className="px-3 py-2.5 border-b border-slate-100 dark:border-white/10 mb-1">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-blue-50 dark:bg-blue-600/20 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/30 flex items-center justify-center font-bold text-xs uppercase">
                    {username.charAt(0)}
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="text-xs font-bold text-slate-900 dark:text-white truncate">{username}</span>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono">Founder Beta</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Profile & Preferences Section */}
              <div className="px-3 pt-1 pb-0.5">
                <span className="text-[10px] font-mono uppercase font-bold tracking-wider text-slate-400 dark:text-neutral-500">
                  Profile & Preferences
                </span>
              </div>

              {/* Settings */}
              <button
                type="button"
                onClick={() => handleOpenTab('settings')}
                className={`w-full flex items-center justify-between px-3 py-2 text-xs rounded-xl transition text-left ${
                  activeTab === 'settings'
                    ? 'bg-blue-50 text-blue-700 font-bold dark:bg-blue-950/50 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30'
                    : 'text-slate-700 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-300 dark:hover:text-white dark:hover:bg-white/10 font-medium'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Settings className="w-4 h-4 text-cyan-600 dark:text-cyan-400 shrink-0" />
                  <span>Settings</span>
                </div>
                <span className="text-[10px] font-mono text-slate-400 dark:text-neutral-500">Tokens & AI</span>
              </button>

              {/* Platform Admin Console (Superuser only) */}
              {subscriptionInfo?.is_admin && (
                <button
                  type="button"
                  onClick={() => handleOpenTab('admin')}
                  className={`w-full flex items-center justify-between px-3 py-2 text-xs rounded-xl transition text-left ${
                    activeTab === 'admin'
                      ? 'bg-purple-50 text-purple-700 font-bold dark:bg-purple-950/50 dark:text-purple-200 border border-purple-200 dark:border-purple-500/30'
                      : 'text-slate-700 hover:text-slate-900 hover:bg-purple-50/70 dark:text-neutral-200 dark:hover:text-white dark:hover:bg-purple-500/10 font-semibold'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <ShieldCheck className="w-4 h-4 text-purple-600 dark:text-purple-400 shrink-0" />
                    <span>Admin Console</span>
                  </div>
                  <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-500/25 dark:text-purple-200">
                    GOD MODE
                  </span>
                </button>
              )}

              {/* Billing */}
              <button
                type="button"
                onClick={() => handleOpenTab('billing')}
                className={`w-full flex items-center justify-between px-3 py-2 text-xs rounded-xl transition text-left ${
                  activeTab === 'billing'
                    ? 'bg-blue-50 text-blue-700 font-bold dark:bg-blue-950/50 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30'
                    : 'text-slate-700 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-300 dark:hover:text-white dark:hover:bg-white/10 font-medium'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <CreditCard className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0" />
                  <span>Billing & Plans</span>
                </div>
                <span
                  className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-full ${
                    subscriptionInfo?.free_beta_mode
                      ? 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300'
                      : subscriptionInfo?.trial_active
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300'
                      : subscriptionInfo?.trial_expired && (subscriptionInfo?.tier || planTier) === 'starter'
                      ? 'bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300'
                      : 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300'
                  }`}
                >
                  {subscriptionInfo?.free_beta_mode
                    ? 'FREE BETA'
                    : subscriptionInfo?.trial_active
                    ? `${subscriptionInfo.trial_days_remaining ?? 15}d TRIAL`
                    : (subscriptionInfo?.tier || planTier || 'pro').toUpperCase()}
                </span>
              </button>

              {/* Support via UPI */}
              {onOpenSupportUpi && (
                <button
                  type="button"
                  onClick={() => {
                    setIsMenuOpen(false);
                    onOpenSupportUpi();
                  }}
                  className="w-full flex items-center justify-between px-3 py-2 text-xs rounded-xl transition text-left bg-gradient-to-r from-amber-50/80 to-rose-50/70 hover:from-amber-100/90 hover:to-rose-100/80 text-amber-950 border border-amber-200/80 dark:from-amber-950/35 dark:to-rose-950/30 dark:hover:from-amber-900/45 dark:hover:to-rose-900/40 dark:text-amber-100 dark:border-amber-500/30 font-semibold"
                >
                  <div className="flex items-center gap-2.5">
                    <Heart className="w-4 h-4 text-rose-500 fill-rose-500 shrink-0" />
                    <span>Support via UPI</span>
                  </div>
                  <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-full bg-gradient-to-r from-amber-500 to-rose-500 text-white shadow-xs">
                    TIP • UPI
                  </span>
                </button>
              )}

              {/* Divider */}
              <div className="h-px bg-slate-100 dark:bg-white/10 my-1" />

              {/* Sign Out Option */}
              <button
                type="button"
                onClick={handleExplicitLogout}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:text-rose-400 dark:hover:text-rose-300 dark:hover:bg-rose-950/40 rounded-xl transition font-medium text-left cursor-pointer active:scale-98"
              >
                <LogOut className="w-4 h-4" />
                <span>Sign Out</span>
              </button>
              </div>
            </>
          )}
        </div>

        {/* Mobile Hamburger Menu Toggle */}
        {onToggleMobileMenu && (
          <button
            type="button"
            onClick={onToggleMobileMenu}
            className="md:hidden w-9 h-9 rounded-xl flex items-center justify-center text-slate-700 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-300 dark:hover:text-white dark:hover:bg-white/5 transition active:scale-95"
            title="Open Mobile Menu"
            aria-label="Open Mobile Menu"
          >
            <Menu className="w-5 h-5" />
          </button>
        )}
      </div>
    </header>
  );
};
