import React, { useState, useEffect, useCallback } from 'react';
import { 
  Coins, DollarSign, TrendingUp, Award, ExternalLink, Search, 
  Filter, Sparkles, CheckCircle2, ArrowRight, ShieldCheck, 
  Terminal, AlertCircle, RefreshCw, Layers
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
    <div className="space-y-6 animate-fade-in-up">
      {/* Toast */}
      {successToast && (
        <div className="fixed bottom-6 right-6 z-50 px-4 py-3 rounded-2xl bg-emerald-950 border border-emerald-500/40 text-emerald-300 text-xs font-semibold shadow-2xl flex items-center gap-2 animate-bounce">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{successToast}</span>
        </div>
      )}

      {/* Hero Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shadow-lg shadow-amber-500/10">
              <Coins className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-extrabold text-white flex items-center gap-2">
                Open Source Bounty Hunter Hub
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-emerald-950/60 text-emerald-400 border border-emerald-500/30 font-bold">
                  Polar.sh &bull; Algora
                </span>
              </h1>
              <p className="text-xs text-neutral-400 mt-0.5">
                Earn real cash rewards by solving high-value issues across verified open-source codebases.
              </p>
            </div>
          </div>
        </div>

        <button
          onClick={handleSync}
          disabled={syncing}
          className="self-start md:self-auto px-3.5 py-2 rounded-xl bg-[#080808] border border-white/10 hover:border-white/20 text-neutral-300 hover:text-white text-xs font-semibold flex items-center gap-1.5 transition active:scale-95 disabled:opacity-50"
          title="Refresh bounties from Polar.sh and Algora feeds"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
          <span>{syncing ? 'Syncing...' : 'Sync Live Bounties'}</span>
        </button>
      </div>

      {/* Financial Metrics Cards */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          <div className="p-4 rounded-2xl bg-[#080808] border border-white/10 flex items-center justify-between shadow-xl">
            <div>
              <span className="text-[11px] font-mono uppercase text-neutral-400">Total Available</span>
              <div className="text-2xl font-extrabold text-emerald-400 mt-0.5">
                {formatCurrency(stats.total_available_usd)}
              </div>
              <span className="text-[10px] text-neutral-500 font-mono">Unclaimed cash rewards</span>
            </div>
            <div className="w-10 h-10 rounded-xl bg-emerald-950/40 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <DollarSign className="w-5 h-5" />
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-[#080808] border border-white/10 flex items-center justify-between shadow-xl">
            <div>
              <span className="text-[11px] font-mono uppercase text-neutral-400">Average Payout</span>
              <div className="text-2xl font-extrabold text-white mt-0.5">
                {formatCurrency(stats.average_bounty_usd)}
              </div>
              <span className="text-[10px] text-neutral-500 font-mono">Per verified ticket</span>
            </div>
            <div className="w-10 h-10 rounded-xl bg-amber-950/40 border border-amber-500/30 flex items-center justify-center text-amber-400">
              <TrendingUp className="w-5 h-5" />
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-[#080808] border border-white/10 flex items-center justify-between shadow-xl">
            <div>
              <span className="text-[11px] font-mono uppercase text-neutral-400">My Claimed Payouts</span>
              <div className="text-2xl font-extrabold text-cyan-400 mt-0.5">
                {formatCurrency(stats.potential_earnings_usd)}
              </div>
              <span className="text-[10px] text-neutral-500 font-mono">{stats.claimed_bounties_count} tasks in-flight</span>
            </div>
            <div className="w-10 h-10 rounded-xl bg-cyan-950/40 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Award className="w-5 h-5" />
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-[#080808] border border-white/10 flex items-center justify-between shadow-xl">
            <div>
              <span className="text-[11px] font-mono uppercase text-neutral-400">Total Bounties</span>
              <div className="text-2xl font-extrabold text-white mt-0.5">
                {stats.total_bounties_count}
              </div>
              <span className="text-[10px] text-neutral-500 font-mono">Leading: {stats.top_platform.toUpperCase()}</span>
            </div>
            <div className="w-10 h-10 rounded-xl bg-purple-950/40 border border-purple-500/30 flex items-center justify-center text-purple-400">
              <Sparkles className="w-5 h-5" />
            </div>
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="p-3 sm:p-4 rounded-2xl bg-[#080808] border border-white/10 flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
        <div className="flex-1 relative">
          <Search className="w-4 h-4 text-neutral-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search bounties by keyword, repository, or language..."
            className="w-full bg-[#000000] border border-white/10 rounded-xl pl-9 pr-3.5 py-2 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white transition"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1 md:pb-0">
          {/* Platform Filter */}
          <div className="flex items-center bg-[#000000] p-1 rounded-xl border border-white/10 shrink-0">
            {['all', 'polar', 'algora'].map((plat) => (
              <button
                key={plat}
                onClick={() => setSelectedPlatform(plat)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold capitalize transition ${
                  selectedPlatform === plat
                    ? 'bg-white text-black shadow-sm'
                    : 'text-neutral-400 hover:text-white'
                }`}
              >
                {plat === 'all' ? 'All Platforms' : plat === 'polar' ? 'Polar.sh' : 'Algora'}
              </button>
            ))}
          </div>

          {/* Min Amount Filter */}
          <select
            value={minAmount}
            onChange={(e) => setMinAmount(Number(e.target.value))}
            className="px-3 py-2 rounded-xl bg-[#000000] border border-white/10 text-xs text-neutral-300 focus:outline-none focus:border-white shrink-0 cursor-pointer"
          >
            <option value={0}>Any Amount</option>
            <option value={200}>$200+ USD</option>
            <option value={400}>$400+ USD</option>
            <option value={600}>$600+ USD</option>
            <option value={1000}>$1,000+ USD</option>
          </select>

          {/* Sort By */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="px-3 py-2 rounded-xl bg-[#000000] border border-white/10 text-xs text-neutral-300 focus:outline-none focus:border-white shrink-0 cursor-pointer"
          >
            <option value="amount_desc">Highest Payout</option>
            <option value="ranking_score">Ranking Score</option>
            <option value="newest">Newest First</option>
          </select>
        </div>
      </div>

      {/* Bounties Listing */}
      {loading ? (
        <div className="p-16 text-center text-neutral-500 flex flex-col items-center gap-3">
          <div className="w-7 h-7 border-2 border-white border-t-transparent rounded-full animate-spin" />
          <span className="text-xs">Scanning Polar.sh and Algora bounty feeds...</span>
        </div>
      ) : bounties.length === 0 ? (
        <div className="p-16 text-center text-neutral-500 rounded-2xl bg-[#080808] border border-white/10">
          <Coins className="w-10 h-10 mx-auto mb-2 text-neutral-600" />
          <p className="text-sm font-semibold text-neutral-300">No bounties match your criteria</p>
          <p className="text-xs text-neutral-500 mt-1 max-w-sm mx-auto">
            Try adjusting your minimum payout filter or platform selection to uncover more cash tickets.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {bounties.map((b) => {
            const isClaimed = b.bounty_status === 'CLAIMED' || Boolean(b.active_task);
            const isClaiming = claimingId === b.id;
            const platformName = b.bounty_platform?.toLowerCase() === 'algora' ? 'Algora' : 'Polar.sh';

            return (
              <div 
                key={b.id}
                className="p-5 rounded-2xl bg-[#080808] border border-white/10 hover:border-white/20 transition flex flex-col justify-between shadow-xl space-y-4 group"
              >
                <div className="space-y-3">
                  {/* Top Bar: Reward Badge & Platform */}
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="px-3 py-1 rounded-xl bg-emerald-950/70 border border-emerald-500/40 text-emerald-300 font-extrabold text-sm flex items-center gap-1 shadow-md">
                        <DollarSign className="w-4 h-4 text-emerald-400 stroke-[2.5]" />
                        <span>{b.bounty_amount}</span>
                        <span className="text-[10px] text-emerald-400/80 uppercase font-mono">{b.bounty_currency || 'USD'}</span>
                      </span>

                      <span className={`text-[10px] font-mono px-2.5 py-0.5 rounded-full border font-bold uppercase ${
                        b.bounty_platform?.toLowerCase() === 'algora'
                          ? 'bg-rose-950/50 text-rose-300 border-rose-500/30'
                          : 'bg-blue-950/50 text-blue-300 border-blue-500/30'
                      }`}>
                        {platformName}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      {isClaimed && (
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-cyan-950/60 text-cyan-300 border border-cyan-500/30 font-semibold flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3 text-cyan-400" />
                          <span>CLAIMED</span>
                        </span>
                      )}

                      <span className="text-[11px] font-mono text-neutral-400">
                        Score: {Math.round(b.ranking_score || 90)}
                      </span>
                    </div>
                  </div>

                  {/* Title & Repo */}
                  <div>
                    <div className="text-[11px] font-mono text-neutral-400 flex items-center gap-1.5 mb-1">
                      <span className="font-semibold text-neutral-200">{b.repository?.owner}/{b.repository?.name}</span>
                      <span>&bull;</span>
                      <span>#{b.issue_number}</span>
                    </div>
                    <h3 className="text-sm font-bold text-white group-hover:text-amber-300 transition line-clamp-2">
                      {b.title}
                    </h3>
                  </div>

                  {/* Description preview */}
                  {b.body && (
                    <p className="text-xs text-neutral-400 line-clamp-2 leading-relaxed">
                      {b.body}
                    </p>
                  )}

                  {/* Metadata Chips */}
                  <div className="flex items-center gap-2 flex-wrap text-[11px] font-mono text-neutral-400 pt-1">
                    {b.difficulty_estimate && (
                      <span className="px-2 py-0.5 rounded-md bg-neutral-900 border border-white/10 capitalize">
                        {b.difficulty_estimate}
                      </span>
                    )}
                    {b.estimated_effort_hours && (
                      <span className="px-2 py-0.5 rounded-md bg-neutral-900 border border-white/10">
                        ~{b.estimated_effort_hours}h effort
                      </span>
                    )}
                    {b.repository?.primary_language && (
                      <span className="px-2 py-0.5 rounded-md bg-neutral-900 border border-white/10 text-neutral-300">
                        {b.repository.primary_language}
                      </span>
                    )}
                  </div>
                </div>

                {/* Bottom Actions */}
                <div className="pt-3 border-t border-white/5 flex items-center justify-between gap-3">
                  <a
                    href={b.bounty_url || b.html_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-neutral-400 hover:text-white flex items-center gap-1 transition"
                    title="View bounty proof and requirements on external platform"
                  >
                    <span>View on {platformName}</span>
                    <ExternalLink className="w-3 h-3 text-neutral-500" />
                  </a>

                  {isClaimed ? (
                    <button
                      onClick={onNavigateToTracker}
                      className="px-4 py-2 rounded-xl bg-cyan-950/60 hover:bg-cyan-900/60 text-cyan-300 border border-cyan-500/30 font-semibold text-xs transition flex items-center gap-1.5 active:scale-95"
                    >
                      <Layers className="w-3.5 h-3.5" />
                      <span>View in Tracker</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => handleClaim(b)}
                      disabled={isClaiming}
                      className="px-4 py-2 rounded-xl bg-white text-black hover:bg-neutral-200 font-bold text-xs transition flex items-center gap-1.5 active:scale-95 shadow-lg disabled:opacity-50"
                    >
                      <span>{isClaiming ? 'Claiming & Prepping...' : 'Claim & Prepare Worktree'}</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
