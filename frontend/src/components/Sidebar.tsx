import React from 'react';
import { 
  Search, Trophy, Bookmark, GitPullRequest, 
  Clock, Play, CreditCard, Settings as SettingsIcon,
  Zap, ArrowRight, BookOpen, PanelLeftClose, PanelLeft
} from 'lucide-react';
import { BrandIcon } from './BrandIcon';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: any) => void;
  totalIssues?: number;
  totalPRs?: number;
  trackedTasksCount?: number;
  onOpenUpgrade?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  totalIssues = 744,
  totalPRs = 0,
  trackedTasksCount = 0,
  onOpenUpgrade,
  isCollapsed = false,
  onToggleCollapse
}) => {
  const navItems = [
    { id: 'issues', label: 'Find Issues', icon: Search, badge: totalIssues > 0 ? String(totalIssues) : '744', badgeType: 'neutral' },
    { id: 'bounties', label: 'Bounties', icon: Trophy, badge: '$$$', badgeType: 'gold' },
    { id: 'tracker', label: 'Tracked Items', icon: Bookmark, badge: trackedTasksCount > 0 ? String(trackedTasksCount) : undefined },
    { id: 'prs', label: 'Pull Requests', icon: GitPullRequest, badge: totalPRs > 0 ? String(totalPRs) : undefined },
    { id: 'history', label: 'Timeline', icon: Clock },
    { id: 'runners', label: 'Runners', icon: Play },
    { id: 'billing', label: 'Billing', icon: CreditCard },
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
  ];

  return (
    <aside
      className={`bg-white dark:bg-[#080c14] border-r border-slate-200 dark:border-white/10 flex flex-col h-screen fixed left-0 top-0 bottom-0 select-none z-30 transition-all duration-300 ease-in-out ${
        isCollapsed ? 'w-20 p-3 items-center' : 'w-64 p-4'
      }`}
    >
      {/* Brand Header & Toggle */}
      {isCollapsed ? (
        <div className="flex flex-col items-center gap-2.5 py-2 mb-4 w-full">
          <div
            className="cursor-pointer p-1.5 rounded-xl hover:bg-slate-100 dark:hover:bg-white/5 transition"
            onClick={() => setActiveTab('issues')}
            title="Issue-to-PR"
          >
            <BrandIcon size={28} showBadge={false} className="text-cyan-500 dark:text-cyan-400" />
          </div>
          <button
            type="button"
            onClick={onToggleCollapse}
            className="w-8 h-8 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/10 transition border border-transparent hover:border-slate-200 dark:hover:border-white/10"
            title="Expand sidebar"
          >
            <PanelLeft className="w-4 h-4 text-slate-600 dark:text-neutral-300" />
          </button>
        </div>
      ) : (
        <div className="flex items-center justify-between px-2 py-2 mb-4">
          <div
            className="flex items-center gap-3 cursor-pointer"
            onClick={() => setActiveTab('issues')}
          >
            <BrandIcon size={30} showBadge={false} className="text-cyan-500 dark:text-cyan-400 shrink-0" />
            <span className="font-extrabold text-base text-slate-900 dark:text-white tracking-tight">
              Issue-to-PR
            </span>
          </div>
          <button
            type="button"
            onClick={onToggleCollapse}
            className="w-8 h-8 rounded-xl flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/10 transition border border-transparent hover:border-slate-200 dark:hover:border-white/10"
            title="Collapse sidebar for more workspace"
          >
            <PanelLeftClose className="w-4 h-4 text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white" />
          </button>
        </div>
      )}

      {/* Main Navigation Links */}
      <nav className={`space-y-1.5 flex-1 overflow-y-auto no-scrollbar w-full ${isCollapsed ? 'flex flex-col items-center' : ''}`}>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          if (isCollapsed) {
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                title={`${item.label}${item.badge ? ` (${item.badge})` : ''}`}
                className={`relative w-11 h-11 rounded-xl flex items-center justify-center transition-all duration-150 active:scale-95 group ${
                  isActive
                    ? 'bg-blue-50 text-blue-700 border border-blue-200 shadow-sm dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-500/40 dark:shadow-blue-500/20'
                    : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/5 border border-transparent'
                }`}
              >
                <Icon className={`w-5 h-5 transition-colors ${
                  isActive ? 'text-blue-700 dark:text-blue-400' : 'text-slate-500 dark:text-neutral-400 group-hover:text-slate-900 dark:group-hover:text-white'
                }`} />
                {item.badge && (
                  <span
                    className={`absolute top-2 right-2 w-2 h-2 rounded-full ring-2 ring-white dark:ring-[#080c14] ${
                      item.badgeType === 'gold' ? 'bg-amber-400' : 'bg-blue-500'
                    }`}
                  />
                )}
              </button>
            );
          }

          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all duration-150 active:scale-95 group ${
                isActive
                  ? 'bg-blue-50 text-blue-700 border border-blue-200 shadow-sm dark:bg-blue-950/40 dark:text-white dark:border-blue-500/30 dark:shadow-blue-500/10 font-bold'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/5 border border-transparent'
              }`}
            >
              <div className="flex items-center gap-3">
                <Icon className={`w-4 h-4 transition-colors ${
                  isActive ? 'text-blue-700 dark:text-blue-400' : 'text-slate-500 dark:text-neutral-400 group-hover:text-slate-900 dark:group-hover:text-white'
                }`} />
                <span className={isActive ? 'text-blue-700 dark:text-white font-bold' : ''}>{item.label}</span>
              </div>

              {item.badge && (
                <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${
                  item.badgeType === 'gold'
                    ? 'bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-400/10 dark:text-amber-400 dark:border-amber-400/20'
                    : isActive
                    ? 'bg-blue-100 text-blue-800 border border-blue-300 dark:bg-white/10 dark:text-white dark:border-white/20'
                    : 'bg-slate-100 text-slate-600 dark:bg-neutral-800 dark:text-neutral-300'
                }`}>
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Bottom Context Card */}
      <div className={`mt-auto pt-3 w-full ${isCollapsed ? 'flex justify-center' : ''}`}>
        {isCollapsed ? (
          <button
            onClick={activeTab === 'bounties' ? () => setActiveTab('bounties') : onOpenUpgrade}
            title={activeTab === 'bounties' ? 'Open Source Bounty Hunter Hub' : 'Supercharge your workflow - Upgrade'}
            className="w-11 h-11 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-amber-600 dark:bg-[#0d121f] dark:hover:bg-[#151c30] dark:border-white/10 dark:hover:border-amber-400/40 dark:text-amber-400 flex items-center justify-center transition shadow-sm active:scale-95"
          >
            <Zap className="w-5 h-5 fill-amber-500 text-amber-500" />
          </button>
        ) : activeTab === 'bounties' ? (
          <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 text-xs shadow-sm space-y-2">
            <div className="font-bold text-slate-900 dark:text-white text-xs">
              Open Source Bounty Hunter Hub
            </div>
            <p className="text-[11px] text-slate-500 dark:text-neutral-400 leading-relaxed">
              Find real cash rewards by solving open-source issues.
            </p>
            <button
              onClick={() => setActiveTab('bounties')}
              className="w-full mt-1 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-800 dark:bg-white/5 dark:hover:bg-white/10 dark:border-white/10 dark:text-white text-[11px] font-semibold flex items-center justify-center gap-1.5 transition active:scale-95"
            >
              <span>Learn More</span>
              <ArrowRight className="w-3 h-3 text-slate-500 dark:text-neutral-400" />
            </button>
          </div>
        ) : (
          <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 text-xs shadow-sm space-y-2">
            <div className="flex items-center gap-2 text-slate-900 dark:text-white font-bold text-xs">
              <Zap className="w-3.5 h-3.5 text-amber-500 fill-amber-500 shrink-0" />
              <span>Supercharge your workflow</span>
            </div>
            <p className="text-[11px] text-slate-500 dark:text-neutral-400 leading-relaxed">
              Automate more. Ship faster.
            </p>
            <button
              onClick={onOpenUpgrade}
              className="w-full mt-1 px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white dark:bg-white/10 dark:hover:bg-white/20 dark:text-white border border-blue-600 dark:border-white/10 text-[11px] font-semibold flex items-center justify-center gap-1.5 transition active:scale-95 shadow-sm shadow-blue-600/20"
            >
              <span>Upgrade</span>
              <ArrowRight className="w-3 h-3 text-white" />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

