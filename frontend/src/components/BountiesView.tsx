import React, { useState, useEffect, useCallback } from 'react';
import { 
  Compass, TrendingUp, Bookmark, Box, ExternalLink, Search, 
  RefreshCw, Clock, ArrowRight, ShieldCheck, CheckCircle2
} from 'lucide-react';
import { Issue, BountyStats } from '../types';
import * as api from '../api';

interface BountiesViewProps {
  onStartBountyWork?: (task: any) => void;
  onNavigateToTracker?: () => void;
}

export const BountiesView: React.FC<BountiesViewProps> = ({
  onStartBountyWork,
  onNavigateToTracker
}) => {
  const [bounties, setBounties] = useState<Issue[]>([]);
  const [stats, setStats] = useState<BountyStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedPlatform, setSelectedPlatform] = useState<string>('all');
  const [minAmount, setMinAmount] = useState<number>(0);
  const [sortBy, setSortBy] = useState<string>('amount_desc');
  const [claimingId, setClaimingId] = useState<string | null>(null);
  const [successToast, setSuccessToast] = useState<string | null>(null);

  const loadBounties = useCallback(async () => {
    try {
      setLoading(true);
      const [list, metrics] = await Promise.all([
        api.fetchBounties({
          platform: selectedPlatform,
          min_amount: minAmount,
          search: searchTerm || undefined,
          sort_by: sortBy
        }),
        api.fetchBountyStats()
      ]);
      setBounties(list);
      setStats(metrics);
    } catch (err: any) {
      console.error('Error fetching bounties:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedPlatform, minAmount, searchTerm, sortBy]);

  useEffect(() => {
    loadBounties();
  }, [loadBounties]);

  const handleSync = async () => {
    try {
      setSyncing(true);
      await api.syncBounties();
      await loadBounties();
      setSuccessToast('✓ Live bounties synchronized successfully.');
      setTimeout(() => setSuccessToast(null), 3000);
    } catch (err: any) {
      console.error('Error syncing bounties:', err);
    } finally {
      setSyncing(false);
    }
  };

  const handleClaim = async (issue: Issue) => {
    try {
      setClaimingId(issue.id);
      const res = await api.startBountyWork(issue.id, 'Claimed via Bounty Hunter Hub');
      setSuccessToast(`🎉 Claimed $${issue.bounty_amount} bounty on ${issue.repository?.name}! Worktree prepared.`);
      setTimeout(() => setSuccessToast(null), 4000);
      
      if (onStartBountyWork) {
        onStartBountyWork(res);
      }
      if (onNavigateToTracker) {
        setTimeout(onNavigateToTracker, 600);
      } else {
        await loadBounties();
      }
    } catch (err: any) {
      alert(`Could not claim bounty: ${err.message}`);
    } finally {
      setClaimingId(null);
    }
  };

  const formatCurrency = (amt: number) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(amt);
  };

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {successToast && (
        <div className="fixed bottom-6 right-6 z-50 px-4 py-3 rounded-2xl bg-emerald-950 border border-emerald-500/40 text-emerald-300 text-xs font-semibold shadow-2xl flex items-center gap-2 animate-bounce">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{successToast}</span>
        </div>
      )}

      {/* Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
              Open Source Bounty Hunter Hub
            </h1>
            <div className="flex items-center gap-1.5">
              <span className="px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200 dark:bg-neutral-800 dark:text-neutral-300 dark:border-transparent font-mono text-[10px] font-bold">
                POLAR.SH
              </span>
              <span className="px-2 py-0.5 rounded-md bg-rose-50 text-rose-700 border border-rose-200 dark:bg-neutral-800 dark:text-neutral-300 dark:border-transparent font-mono text-[10px] font-bold">
                ALGORA
              </span>
            </div>
          </div>
          <p className="text-xs text-slate-500 dark:text-neutral-400 mt-1">
            Earn real cash rewards by solving high-value issues across verified open-source codebases.
          </p>
        </div>

        <button
          onClick={handleSync}
          disabled={syncing}
          className="self-start sm:self-auto px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-neutral-200 hover:text-white text-xs font-semibold flex items-center gap-2 transition active:scale-95 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
          <span>{syncing ? 'Syncing...' : 'Sync Live Bounties'}</span>
        </button>
      </div>

      {/* 4 Financial Metrics Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {/* 1. Total Available */}
        <div className="p-4 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 flex items-center justify-between shadow-sm dark:shadow-xl">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 font-bold">Total Available</span>
            <div className="text-2xl font-black text-slate-900 dark:text-white mt-0.5 font-mono">
              {stats ? formatCurrency(stats.total_available_usd) : '$4,050'}
            </div>
            <span className="text-[11px] text-neutral-500">Unclaimed cash rewards</span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-neutral-400 shrink-0">
            <Compass className="w-5 h-5 text-neutral-300" />
          </div>
        </div>

        {/* 2. Average Payout */}
        <div className="p-4 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 flex items-center justify-between shadow-sm dark:shadow-xl">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 font-bold">Average Payout</span>
            <div className="text-2xl font-black text-slate-900 dark:text-white mt-0.5 font-mono">
              {stats ? formatCurrency(stats.average_bounty_usd) : '$694'}
            </div>
            <span className="text-[11px] text-neutral-500">Per verified ticket</span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-neutral-400 shrink-0">
            <TrendingUp className="w-5 h-5 text-neutral-300" />
          </div>
        </div>

        {/* 3. My Claimed Payouts */}
        <div className="p-4 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 flex items-center justify-between shadow-sm dark:shadow-xl">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 font-bold">My Claimed Payouts</span>
            <div className="text-2xl font-black text-slate-900 dark:text-white mt-0.5 font-mono">
              {stats ? formatCurrency(stats.potential_earnings_usd) : '$1,500'}
            </div>
            <span className="text-[11px] text-neutral-500">{stats?.claimed_bounties_count ?? 1} tasks in-flight</span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-neutral-400 shrink-0">
            <Bookmark className="w-5 h-5 text-neutral-300" />
          </div>
        </div>

        {/* 4. Total Bounties */}
        <div className="p-4 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 flex items-center justify-between shadow-sm dark:shadow-xl">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 font-bold">Total Bounties</span>
            <div className="text-2xl font-black text-slate-900 dark:text-white mt-0.5 font-mono">
              {stats?.total_bounties_count ?? 8}
            </div>
            <span className="text-[11px] text-neutral-500">Leading: POLAR</span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-neutral-400 shrink-0">
            <Box className="w-5 h-5 text-neutral-300" />
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-3 sm:p-4 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between shadow-sm dark:shadow-xl">
        <div className="flex-1 relative">
          <Search className="w-4 h-4 text-neutral-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search bounties by keyword, repository, or language..."
            className="w-full bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl pl-10 pr-3.5 py-2 text-xs text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto no-scrollbar">
          {/* Platforms Dropdown / Pills */}
          <select
            value={selectedPlatform}
            onChange={(e) => setSelectedPlatform(e.target.value)}
            className="bg-[#05080f] border border-white/10 rounded-xl px-3 py-2 text-xs text-neutral-300 focus:outline-none focus:border-white"
          >
            <option value="all">All Platforms</option>
            <option value="polar">Polar.Sh</option>
            <option value="algora">Algora</option>
          </select>

          <button
            onClick={() => setSelectedPlatform('polar')}
            className={`px-3 py-2 rounded-xl text-xs font-semibold transition ${
              selectedPlatform === 'polar'
                ? 'bg-blue-600 text-white font-bold'
                : 'bg-[#05080f] border border-white/10 text-neutral-400 hover:text-white'
            }`}
          >
            Polar.Sh
          </button>

          <button
            onClick={() => setSelectedPlatform('algora')}
            className={`px-3 py-2 rounded-xl text-xs font-semibold transition ${
              selectedPlatform === 'algora'
                ? 'bg-rose-600 text-white font-bold'
                : 'bg-[#05080f] border border-white/10 text-neutral-400 hover:text-white'
            }`}
          >
            Algora
          </button>

          <select
            value={minAmount}
            onChange={(e) => setMinAmount(Number(e.target.value))}
            className="bg-[#05080f] border border-white/10 rounded-xl px-3 py-2 text-xs text-neutral-300 focus:outline-none focus:border-white"
          >
            <option value={0}>Any Amount</option>
            <option value={200}>$200+</option>
            <option value={500}>$500+</option>
            <option value={1000}>$1000+</option>
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="bg-[#05080f] border border-white/10 rounded-xl px-3 py-2 text-xs text-neutral-300 focus:outline-none focus:border-white"
          >
            <option value="amount_desc">Highest Payout</option>
            <option value="created_desc">Newest</option>
            <option value="score_desc">Best Score</option>
          </select>
        </div>
      </div>

      {/* 2-Column Grid of Bounty Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {bounties.map((bounty) => {
          const isClaiming = claimingId === bounty.id;
          const isClaimed = Boolean((bounty as any).is_bounty_claimed || (bounty as any).task_id);

          return (
            <div 
              key={bounty.id}
              className="p-5 rounded-2xl bg-[#0c101a] hover:bg-[#0e1320] border border-white/10 hover:border-white/20 shadow-xl transition space-y-3.5 flex flex-col justify-between"
            >
              <div className="space-y-2.5">
                {/* Badges row & Score */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-1 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30 text-xs font-bold font-mono">
                      $ {bounty.bounty_amount || 600} USD
                    </span>
                    <span className={`px-2.5 py-1 rounded-lg font-mono text-[11px] font-bold ${
                      bounty.bounty_platform === 'algora'
                        ? 'bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/60 dark:text-rose-400 dark:border-rose-500/30'
                        : 'bg-blue-50 text-blue-700 border border-blue-200 dark:bg-neutral-800 dark:text-neutral-300'
                    }`}>
                      {bounty.bounty_platform === 'algora' ? 'ALGORA' : 'POLAR.SH'}
                    </span>
                  </div>

                  <span className="text-xs font-mono text-neutral-400">
                    Score: {bounty.ranking_score?.toFixed(0) || 95}
                  </span>
                </div>

                {/* Repo and Issue # */}
                <div className="text-xs text-neutral-400 font-mono">
                  {bounty.repository?.full_name || bounty.repository?.name} • #{bounty.issue_number}
                </div>

                {/* Title */}
                <h3 className="text-sm font-bold text-slate-900 dark:text-white leading-snug line-clamp-2">
                  {bounty.title}
                </h3>

                {/* Description */}
                <p className="text-xs text-neutral-400 leading-relaxed line-clamp-2">
                  {bounty.body}
                </p>

                {/* Tags: Difficulty, Effort, Language */}
                <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                  <span className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-neutral-300 flex items-center gap-1.5">
                    <span>📶</span>
                    <span className="capitalize">{bounty.difficulty_estimate || 'Intermediate'}</span>
                  </span>
                  <span className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-neutral-300 flex items-center gap-1">
                    <Clock className="w-3 h-3 text-neutral-400" />
                    <span>~{bounty.estimated_effort_hours || 12}h effort</span>
                  </span>
                  <span className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-neutral-300 flex items-center gap-1">
                    <span>🐍</span>
                    <span>{bounty.repository?.primary_language || 'Python'}</span>
                  </span>
                </div>
              </div>

              {/* Bottom Actions */}
              <div className="flex items-center justify-between gap-3 pt-3 border-t border-white/5">
                <a
                  href={bounty.bounty_url || bounty.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-neutral-400 hover:text-white flex items-center gap-1.5 transition"
                >
                  <ExternalLink className="w-3.5 h-3.5 text-neutral-400" />
                  <span>View on {bounty.bounty_platform === 'algora' ? 'Algora' : 'Polar.sh'}</span>
                </a>

                {isClaimed ? (
                  <button
                    onClick={onNavigateToTracker}
                    className="px-4 py-2 rounded-xl border border-blue-500/40 text-blue-400 hover:bg-blue-500/10 text-xs font-semibold flex items-center gap-1.5 transition active:scale-95"
                  >
                    <span>View in Tracker</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                ) : (
                  <button
                    onClick={() => handleClaim(bounty)}
                    disabled={isClaiming}
                    className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white dark:bg-white dark:hover:bg-neutral-200 dark:text-black font-bold text-xs flex items-center gap-1.5 shadow-md shadow-blue-600/20 transition active:scale-95 disabled:opacity-50"
                  >
                    <span>{isClaiming ? 'Preparing Worktree...' : 'Claim & Prepare Worktree'}</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
