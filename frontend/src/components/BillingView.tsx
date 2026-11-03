import React, { useState, useEffect } from 'react';
import { 
  CreditCard, Sparkles, Check, ExternalLink, Zap, 
  ShieldCheck, AlertCircle, RefreshCw, Loader2, ArrowRight
} from 'lucide-react';
import { BillingPlan, SubscriptionInfo } from '../types';
import * as api from '../api';

export function BillingView() {
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [subInfo, setSubInfo] = useState<SubscriptionInfo | null>(null);
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('monthly');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadBillingData = async () => {
    try {
      const [plansData, subData] = await Promise.all([
        api.fetchBillingPlans(),
        api.fetchSubscriptionInfo(),
      ]);
      setPlans(plansData);
      setSubInfo(subData);
    } catch (err: any) {
      console.error('Failed to load billing details:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBillingData();
  }, []);

  const handleCheckout = async (planTier: 'pro' | 'team') => {
    setActionLoading(`checkout_${planTier}`);
    setMessage(null);
    try {
      const session = await api.createCheckoutSession(planTier, billingCycle);
      if (session.checkout_url) {
        window.location.href = session.checkout_url;
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Failed to start checkout' });
      setActionLoading(null);
    }
  };

  const handleOpenPortal = async () => {
    setActionLoading('portal');
    setMessage(null);
    try {
      const portal = await api.createPortalSession();
      if (portal.portal_url) {
        window.location.href = portal.portal_url;
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Failed to open customer portal' });
      setActionLoading(null);
    }
  };

  const handleSimulateTier = async (targetTier: 'starter' | 'pro' | 'team') => {
    setActionLoading(`sim_${targetTier}`);
    setMessage(null);
    try {
      const updated = await api.simulateTierChange(targetTier);
      setSubInfo(updated);
      setMessage({ 
        type: 'success', 
        text: `✓ Simulation: Workspace switched to ${targetTier.toUpperCase()} tier successfully.` 
      });
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Simulation switch failed' });
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] p-8 text-neutral-400">
        <Loader2 className="w-8 h-8 animate-spin mb-3 text-white" />
        <p className="text-sm">Loading subscription and pricing plans...</p>
      </div>
    );
  }

  const currentTier = subInfo?.tier || 'starter';
  const usageCount = subInfo?.tasks_created_this_month ?? 0;
  const limitCount = subInfo?.monthly_task_limit ?? 5;
  const isUnlimited = limitCount === null;
  const usagePct = isUnlimited ? 0 : Math.min(100, Math.round((usageCount / limitCount) * 100));

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8 animate-in fade-in duration-200">
      {/* Header & Status Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="p-1.5 rounded-lg bg-neutral-900 border border-white/10 text-white">
              <CreditCard className="w-4 h-4" />
            </span>
            <h1 className="text-2xl font-bold text-white tracking-tight">Billing & Plans</h1>
          </div>
          <p className="text-sm text-neutral-400">
            Scale your autonomous issue triage, worktree generation, and Antigravity workflow.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleOpenPortal}
            disabled={actionLoading === 'portal'}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-neutral-900 border border-white/10 hover:border-white/20 text-neutral-200 text-xs font-semibold hover:bg-neutral-800 transition active:scale-95 disabled:opacity-50"
          >
            {actionLoading === 'portal' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <ExternalLink className="w-3.5 h-3.5" />
            )}
            <span>Stripe Customer Portal</span>
          </button>
        </div>
      </div>

      {message && (
        <div className={`p-4 rounded-xl border text-xs font-medium flex items-center justify-between ${
          message.type === 'success' 
            ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
            : 'bg-rose-500/10 border-rose-500/20 text-rose-300'
        }`}>
          <span>{message.text}</span>
          <button onClick={() => setMessage(null)} className="underline ml-4 hover:opacity-80">Dismiss</button>
        </div>
      )}

      {/* Monthly Task Meter & Active Tier Snapshot */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Current Plan Card */}
        <div className="p-5 rounded-2xl bg-neutral-950 border border-white/10 relative overflow-hidden">
          <div className="text-xs uppercase tracking-wider text-neutral-400 font-semibold mb-1">
            Current Tier
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold text-white capitalize">
              {currentTier === 'starter' ? 'Community Starter' : currentTier === 'pro' ? 'Pro Developer' : 'Engineering Team'}
            </span>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${
              currentTier === 'pro'
                ? 'bg-indigo-500/20 border-indigo-500/30 text-indigo-300'
                : currentTier === 'team'
                ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-300'
                : 'bg-neutral-800 border-white/10 text-neutral-300'
            }`}>
              {subInfo?.status || 'Active'}
            </span>
          </div>
          <p className="text-xs text-neutral-400 mt-2">
            {currentTier === 'starter' 
              ? 'Free tier for personal open-source issue exploration.' 
              : 'Full access to unconstrained PR publication and priority queues.'}
          </p>
        </div>

        {/* Task Quota Progress Card */}
        <div className="md:col-span-2 p-5 rounded-2xl bg-neutral-950 border border-white/10">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs uppercase tracking-wider text-neutral-400 font-semibold">
              Monthly Task Quota
            </div>
            <span className="text-xs font-mono font-bold text-white">
              {isUnlimited ? `${usageCount} tasks created (Unlimited)` : `${usageCount} / ${limitCount} tasks used`}
            </span>
          </div>

          <div className="w-full bg-neutral-900 h-2.5 rounded-full overflow-hidden border border-white/5 mb-2">
            <div 
              className={`h-full transition-all duration-500 ${
                isUnlimited 
                  ? 'bg-indigo-500 w-full' 
                  : usagePct >= 100 
                  ? 'bg-rose-500' 
                  : usagePct >= 80 
                  ? 'bg-amber-500' 
                  : 'bg-emerald-500'
              }`}
              style={{ width: isUnlimited ? '100%' : `${usagePct}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-[11px] text-neutral-400">
            <span>Resets on the 1st of next month</span>
            {!isUnlimited && usagePct >= 80 && (
              <span className="text-amber-400 font-medium">
                {limitCount - usageCount <= 0 ? 'Limit reached' : `${limitCount - usageCount} tasks remaining`}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Pricing Toggle (Monthly vs Annual) */}
      <div className="flex flex-col items-center justify-center gap-2 pt-2">
        <div className="inline-flex items-center bg-neutral-950 p-1 rounded-xl border border-white/10">
          <button
            onClick={() => setBillingCycle('monthly')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition ${
              billingCycle === 'monthly'
                ? 'bg-white text-black shadow-sm'
                : 'text-neutral-400 hover:text-white'
            }`}
          >
            Monthly Billing
          </button>
          <button
            onClick={() => setBillingCycle('annual')}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold transition ${
              billingCycle === 'annual'
                ? 'bg-white text-black shadow-sm'
                : 'text-neutral-400 hover:text-white'
            }`}
          >
            <span>Annual Billing</span>
            <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded-full border border-emerald-500/20">
              Save 17%
            </span>
          </button>
        </div>
      </div>

      {/* Pricing Plans Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {plans.map((plan) => {
          const isCurrent = currentTier === plan.id;
          const isPro = plan.id === 'pro';
          const isTeam = plan.id === 'team';
          const price = billingCycle === 'annual' ? plan.price_annual : plan.price_monthly;
          const billingSuffix = plan.price_monthly === 0 
            ? 'forever' 
            : billingCycle === 'annual' 
            ? '/ year' 
            : '/ month';

          return (
            <div
              key={plan.id}
              className={`relative flex flex-col justify-between p-6 sm:p-7 rounded-2xl bg-neutral-950 border transition-all duration-200 ${
                isPro 
                  ? 'border-indigo-500/50 shadow-xl shadow-indigo-500/10 ring-1 ring-indigo-500/30' 
                  : 'border-white/10 hover:border-white/20'
              }`}
            >
              {isPro && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 text-white font-bold text-[10px] tracking-wide uppercase shadow-md">
                  Most Popular
                </div>
              )}

              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-lg font-bold text-white">{plan.name}</h3>
                  {isCurrent && (
                    <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                      Active
                    </span>
                  )}
                </div>

                <p className="text-xs text-neutral-400 leading-relaxed min-h-[36px] mb-6">
                  {plan.description}
                </p>

                <div className="flex items-baseline gap-1 mb-6">
                  <span className="text-3xl font-extrabold text-white">${price}</span>
                  <span className="text-xs text-neutral-400 font-medium">{billingSuffix}</span>
                </div>

                <div className="border-t border-white/10 pt-5 space-y-3 mb-6">
                  {plan.features.map((f, i) => (
                    <div key={i} className="flex items-start gap-2.5 text-xs">
                      {f.included ? (
                        <Check className={`w-4 h-4 shrink-0 mt-0.5 ${
                          f.highlight ? 'text-indigo-400' : 'text-emerald-400'
                        }`} />
                      ) : (
                        <span className="w-4 h-4 shrink-0 text-center text-neutral-600 font-bold">—</span>
                      )}
                      <span className={f.included ? (f.highlight ? 'text-white font-semibold' : 'text-neutral-300') : 'text-neutral-500'}>
                        {f.name}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                {isCurrent ? (
                  <button
                    disabled
                    className="w-full py-2.5 px-4 rounded-xl bg-neutral-900 border border-white/10 text-neutral-400 text-xs font-bold cursor-default"
                  >
                    Current Plan
                  </button>
                ) : plan.id === 'starter' ? (
                  <button
                    onClick={() => handleSimulateTier('starter')}
                    disabled={actionLoading !== null}
                    className="w-full py-2.5 px-4 rounded-xl border border-white/10 hover:bg-neutral-900 text-neutral-300 text-xs font-semibold transition"
                  >
                    Downgrade to Starter
                  </button>
                ) : (
                  <button
                    onClick={() => handleCheckout(plan.id as 'pro' | 'team')}
                    disabled={actionLoading !== null}
                    className={`w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-bold transition active:scale-95 shadow-md ${
                      isPro
                        ? 'bg-white text-black hover:bg-neutral-200'
                        : 'bg-neutral-900 hover:bg-neutral-800 text-white border border-white/15'
                    }`}
                  >
                    {actionLoading === `checkout_${plan.id}` ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <>
                        <span>Upgrade to {plan.name}</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Developer Simulation Mode Box (Visible for local testing) */}
      <div className="p-5 rounded-2xl bg-neutral-950/80 border border-dashed border-white/20">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <span className="p-1 rounded bg-amber-500/20 text-amber-400">
              <Zap className="w-4 h-4" />
            </span>
            <span className="text-xs font-bold text-white uppercase tracking-wider">
              Developer Quick Simulation Switcher
            </span>
            <span className="text-[10px] text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-500/20">
              Test Mode
            </span>
          </div>
          <span className="text-[11px] text-neutral-400">
            Instantly toggle organization tiers to verify quota enforcement & UI changes.
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSimulateTier('starter')}
            disabled={actionLoading !== null || currentTier === 'starter'}
            className="px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-neutral-800 border border-white/10 text-xs font-medium text-neutral-200 transition disabled:opacity-40"
          >
            Switch to Starter (5 tasks/mo)
          </button>
          <button
            onClick={() => handleSimulateTier('pro')}
            disabled={actionLoading !== null || currentTier === 'pro'}
            className="px-3 py-1.5 rounded-lg bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-500/30 text-xs font-medium text-indigo-200 transition disabled:opacity-40"
          >
            Switch to Pro (Unlimited)
          </button>
          <button
            onClick={() => handleSimulateTier('team')}
            disabled={actionLoading !== null || currentTier === 'team'}
            className="px-3 py-1.5 rounded-lg bg-emerald-950/60 hover:bg-emerald-900/60 border border-emerald-500/30 text-xs font-medium text-emerald-200 transition disabled:opacity-40"
          >
            Switch to Team (Private & RBAC)
          </button>
        </div>
      </div>
    </div>
  );
}
