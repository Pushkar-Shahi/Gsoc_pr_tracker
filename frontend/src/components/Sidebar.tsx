import React from 'react';
import { 
  Search, Trophy, Bookmark, GitPullRequest, 
  Clock, Play, CreditCard, Settings as SettingsIcon,
  Zap, ArrowRight, BookOpen
} from 'lucide-react';
import { BrandIcon } from './BrandIcon';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: any) => void;
  totalIssues?: number;
  totalPRs?: number;
  trackedTasksCount?: number;
  onOpenUpgrade?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  totalIssues = 744,
  totalPRs = 0,
  trackedTasksCount = 0,
  onOpenUpgrade
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
    <aside className="w-64 bg-[#080c14] border-r border-white/10 flex flex-col h-screen fixed left-0 top-0 bottom-0 p-4 shrink-0 select-none z-30">
      {/* Brand Header */}
      <div className="flex items-center gap-3 px-2 py-3 mb-4 cursor-pointer" onClick={() => setActiveTab('issues')}>
        <BrandIcon size={32} showBadge={false} className="text-cyan-400 shrink-0" />
        <span className="font-extrabold text-lg text-white tracking-tight">
          Issue-to-PR
        </span>
      </div>

      {/* Main Navigation Links */}
      <nav className="space-y-1.5 flex-1 overflow-y-auto no-scrollbar">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all duration-150 active:scale-95 group ${
                isActive
                  ? 'bg-blue-600/10 text-white border border-blue-500/30 shadow-sm shadow-blue-500/10'
                  : 'text-neutral-400 hover:text-white hover:bg-white/5 border border-transparent'
              }`}
            >
              <div className="flex items-center gap-3">
                <Icon className={`w-4 h-4 transition-colors ${
                  isActive ? 'text-blue-400' : 'text-neutral-400 group-hover:text-white'
                }`} />
                <span>{item.label}</span>
              </div>

              {item.badge && (
                <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${
                  item.badgeType === 'gold'
                    ? 'bg-amber-400/10 text-amber-400 border border-amber-400/20'
                    : isActive
                    ? 'bg-white/10 text-white border border-white/20'
                    : 'bg-neutral-800 text-neutral-300'
                }`}>
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Bottom Context Card */}
      <div className="mt-auto pt-4">
        {activeTab === 'bounties' ? (
          <div className="p-3.5 rounded-2xl bg-[#0d121f] border border-white/10 text-xs shadow-lg space-y-2">
            <div className="font-bold text-white text-xs">
              Open Source Bounty Hunter Hub
            </div>
            <p className="text-[11px] text-neutral-400 leading-relaxed">
              Find real cash rewards by solving open-source issues.
            </p>
            <button
              onClick={() => setActiveTab('bounties')}
              className="w-full mt-1 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-white text-[11px] font-semibold flex items-center justify-center gap-1.5 transition active:scale-95"
            >
              <span>Learn More</span>
              <ArrowRight className="w-3 h-3 text-neutral-400" />
            </button>
          </div>
        ) : (
          <div className="p-3.5 rounded-2xl bg-[#0d121f] border border-white/10 text-xs shadow-lg space-y-2">
            <div className="flex items-center gap-2 text-white font-bold text-xs">
              <Zap className="w-3.5 h-3.5 text-amber-400 fill-amber-400 shrink-0" />
              <span>Supercharge your workflow</span>
            </div>
            <p className="text-[11px] text-neutral-400 leading-relaxed">
              Automate more. Ship faster.
            </p>
            <button
              onClick={onOpenUpgrade}
              className="w-full mt-1 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 border border-white/10 text-white text-[11px] font-semibold flex items-center justify-center gap-1.5 transition active:scale-95"
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

