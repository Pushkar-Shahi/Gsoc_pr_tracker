import React, { useState, useEffect, useRef } from 'react';
import {
  CreditCard, Sparkles, Check, Zap, Heart, QrCode,
  ShieldCheck, Clock, XCircle, Loader2, ArrowRight, RefreshCw
} from 'lucide-react';
import { BillingPlan, SubscriptionInfo, UpiConfig, UpiPaymentRequest } from '../types';
import * as api from '../api';
import { UpiPaymentCard } from './UpiPaymentCard';

type ActiveUpiPanel =
  | { mode: 'support' }
  | {
      mode: 'plan';
      planTier: 'pro' | 'team';
      billingCycle: 'monthly' | 'annual';
      amountInr: number;
      planLabel: string;
    }
  | null;

const STATUS_BADGE_MAP: Record<string, string> = {
  pending:
    'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30',
  approved:
    'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30',
  rejected:
    'bg-rose-50 text-rose-800 border-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/30',
};

export function BillingView() {
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [subInfo, setSubInfo] = useState<SubscriptionInfo | null>(null);
  const [upiConfig, setUpiConfig] = useState<UpiConfig | null>(null);
  const [myUpiRequests, setMyUpiRequests] = useState<UpiPaymentRequest[]>([]);
  const [adminUpiRequests, setAdminUpiRequests] = useState<UpiPaymentRequest[]>([]);
  const [adminFilter, setAdminFilter] = useState<'pending' | 'approved' | 'rejected' | 'all'>('pending');

  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('monthly');
  const [activeUpiPanel, setActiveUpiPanel] = useState<ActiveUpiPanel>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const upiPanelRef = useRef<HTMLDivElement>(null);

  const loadBillingData = async (statusFilter: 'pending' | 'approved' | 'rejected' | 'all' = adminFilter) => {
    try {
      const [plansData, subData, configData, myReqs] = await Promise.all([
        api.fetchBillingPlans(),
        api.fetchSubscriptionInfo(),
        api.fetchUpiConfig(),
        api.fetchMyUpiRequests(),
      ]);
      setPlans(plansData);
      setSubInfo(subData);
      setUpiConfig(configData);
      setMyUpiRequests(myReqs);

      if (subData?.is_admin) {
        const adminReqs = await api.fetchAdminUpiRequests(statusFilter).catch(() => []);
        setAdminUpiRequests(adminReqs);
      }
    } catch (err: any) {
      console.error('Failed to load billing details:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBillingData();
    const handleUpiUpdated = () => {
      loadBillingData();
    };
    window.addEventListener('issuetopr-upi-updated', handleUpiUpdated);
    return () => window.removeEventListener('issuetopr-upi-updated', handleUpiUpdated);
  }, []);

  const openUpiCheckout = (plan: BillingPlan) => {
    if (plan.id !== 'pro' && plan.id !== 'team') return;
    const price = billingCycle === 'annual' ? plan.price_annual : plan.price_monthly;
    setMessage(null);
    setActiveUpiPanel({
      mode: 'plan',
      planTier: plan.id,
      billingCycle,
      amountInr: price,
      planLabel: `${plan.name} (${billingCycle === 'annual' ? 'Annual' : 'Monthly'})`,
    });
    setTimeout(() => {
      upiPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
  };

  const openProUpgradePanel = () => {
    const proPlan = plans.find((p) => p.id === 'pro');
    if (proPlan) {
      openUpiCheckout(proPlan);
    } else {
      setMessage(null);
      setActiveUpiPanel({
        mode: 'plan',
        planTier: 'pro',
        billingCycle,
        amountInr: billingCycle === 'annual' ? 1000 : 100,
        planLabel: `Pro Developer (${billingCycle === 'annual' ? 'Annual' : 'Monthly'})`,
      });
      setTimeout(() => {
        upiPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 60);
    }
  };

  const openSupportPanel = () => {
    setMessage(null);
    setActiveUpiPanel({ mode: 'support' });
    setTimeout(() => {
      upiPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
  };

  const handleUpiSubmitted = async (req: UpiPaymentRequest) => {
    setMessage({
      type: 'success',
      text: `✓ UPI payment reference ${req.utr_number} (₹${req.amount_inr}) submitted and queued for verification.`,
    });
    await loadBillingData();
  };

  const handleAdminFilterChange = async (nextFilter: 'pending' | 'approved' | 'rejected' | 'all') => {
    setAdminFilter(nextFilter);
    setActionLoading('admin_refresh');
    try {
      const adminReqs = await api.fetchAdminUpiRequests(nextFilter);
      setAdminUpiRequests(adminReqs);
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Failed to load admin queue' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleAdminReview = async (requestId: string, action: 'approve' | 'reject') => {
    setActionLoading(`review_${requestId}_${action}`);
    setMessage(null);
    try {
      const updated = await api.reviewAdminUpiRequest(requestId, action);
      setMessage({
        type: 'success',
        text:
          action === 'approve'
            ? `✓ Approved UPI payment ${updated.utr_number} (₹${updated.amount_inr})${updated.plan_tier ? ` and activated ${updated.plan_tier.toUpperCase()} tier.` : '.'}`
            : `Marked UPI submission ${updated.utr_number} as rejected.`,
      });
      await loadBillingData(adminFilter);
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message || 'Review action failed' });
    } finally {
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
        text: `✓ Simulation: Workspace switched to ${targetTier.toUpperCase()} tier successfully.`,
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
        <Loader2 className="w-8 h-8 animate-spin mb-3 text-blue-500" />
        <p className="text-sm">Loading subscription, GSoC plans, and UPI billing...</p>
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
      {/* Header & Support UPI CTA */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 dark:border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="p-1.5 rounded-xl bg-blue-50 text-blue-600 border border-blue-200 dark:bg-white/5 dark:border-white/10 dark:text-white">
              <CreditCard className="w-4 h-4" />
            </span>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
              Billing, Support & UPI Payments
            </h1>
          </div>
          <p className="text-sm text-slate-500 dark:text-neutral-400">
            Support GSoC Issue-to-PR or upgrade via Direct UPI ({upiConfig?.upi_vpa || '8116710520@ibl'}) with 0% gateway fees.
          </p>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            type="button"
            onClick={openSupportPanel}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-amber-500 via-orange-500 to-rose-500 hover:from-amber-400 hover:via-orange-400 hover:to-rose-400 text-white text-xs font-bold shadow-md shadow-orange-500/25 transition active:scale-95"
          >
            <Heart className="w-3.5 h-3.5 fill-white" />
            <span>Support via UPI ({upiConfig?.upi_vpa || '8116710520@ibl'})</span>
          </button>
        </div>
      </div>

      {/* Dynamic 15-Day Reverse Free Trial / Plan Status Banner */}
      {subInfo?.trial_active ? (
        (() => {
          const totalDays = subInfo.trial_total_days || 15;
          const daysLeft = Math.max(0, subInfo.trial_days_remaining ?? totalDays);
          const daysUsed = Math.max(1, totalDays - daysLeft + 1);
          const progressPct = Math.min(100, Math.max(8, Math.round((daysLeft / totalDays) * 100)));
          const isUrgent = daysLeft <= 3;

          return (
            <div className={`p-5 rounded-2xl border shadow-sm space-y-4 ${
              isUrgent
                ? 'bg-gradient-to-r from-amber-50 via-orange-50/70 to-white dark:from-amber-950/35 dark:via-orange-950/25 dark:to-[#0c101a] border-amber-300 dark:border-amber-500/40'
                : 'bg-gradient-to-r from-indigo-50/90 via-blue-50/70 to-slate-50 dark:from-indigo-950/40 dark:via-blue-950/30 dark:to-[#0c101a] border-indigo-200 dark:border-indigo-500/30'
            }`}>
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex items-start gap-3.5">
                  <div className={`p-2.5 rounded-xl text-white shrink-0 shadow-sm ${
                    isUrgent ? 'bg-amber-600 shadow-amber-600/30' : 'bg-indigo-600 shadow-indigo-600/30'
                  }`}>
                    <Sparkles className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                        15-Day Pro Developer Reverse Trial Active
                      </h3>
                      <span className={`text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full border ${
                        isUrgent
                          ? 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-400/30'
                          : 'bg-indigo-100 text-indigo-800 border-indigo-200 dark:bg-indigo-500/20 dark:text-indigo-300 dark:border-indigo-400/30'
                      }`}>
                        {daysLeft} {daysLeft === 1 ? 'DAY' : 'DAYS'} LEFT • DAY {Math.min(totalDays, daysUsed)}/{totalDays}
                      </span>
                    </div>
                    <p className="text-xs text-slate-600 dark:text-neutral-300 mt-1 leading-relaxed">
                      Every Pro capability is unlocked right now with zero card required. After day {totalDays}, your workspace automatically moves to Community Starter (5 one-time free credits) unless you lock in Pro for <strong>₹100/month (~₹3.30/day)</strong> via Direct UPI.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={openProUpgradePanel}
                  className="shrink-0 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold shadow-md shadow-indigo-600/20 transition active:scale-95"
                >
                  Lock Pro Unlimited (₹{billingCycle === 'annual' ? '1,000/yr' : '100/mo'})
                </button>
              </div>

              <div className="space-y-1.5">
                <div className="w-full h-2 rounded-full bg-white/80 dark:bg-black/40 border border-slate-200 dark:border-white/10 overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${isUrgent ? 'bg-amber-500' : 'bg-indigo-500'}`}
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500 dark:text-neutral-400">
                  <span>Unlocked during trial: Unlimited PR tasks • Live BYOK AI • Weighted Ranking Matrix • Real-time Webhooks • Priority Runners</span>
                  {subInfo.trial_ends_at && (
                    <span className="font-mono">Ends {new Date(subInfo.trial_ends_at).toLocaleDateString()}</span>
                  )}
                </div>
              </div>
            </div>
          );
        })()
      ) : subInfo?.trial_expired && currentTier === 'starter' ? (
        <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-amber-50/90 via-rose-50/60 to-white dark:from-amber-950/30 dark:via-rose-950/20 dark:to-[#0c101a] border border-amber-300 dark:border-amber-500/35 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-start sm:items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-amber-600 text-white shrink-0 shadow-sm shadow-amber-600/30">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  Your 15-Day Pro Trial Has Ended — Moved to Community Starter
                </h3>
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-400/30">
                  5 ONE-TIME CREDITS
                </span>
              </div>
              <p className="text-xs text-slate-600 dark:text-neutral-300 mt-0.5 leading-relaxed">
                All your saved BYOK keys, filters, and PR history are intact. Restore unlimited tasks, weighted ranking matrix, per-tenant webhooks, and priority runners anytime for ₹100/mo (~₹3.30/day).
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={openProUpgradePanel}
            className="shrink-0 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md shadow-blue-600/20 transition active:scale-95"
          >
            Restore Pro Unlimited
          </button>
        </div>
      ) : (
        <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-blue-50/90 via-indigo-50/70 to-slate-50 dark:from-blue-950/40 dark:via-indigo-950/30 dark:to-[#0c101a] border border-blue-200 dark:border-blue-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-start sm:items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-blue-600 text-white shrink-0 shadow-sm shadow-blue-600/30">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  {subInfo?.free_beta_mode
                    ? 'Public Launch Special: GSoC 2026 Early Adopter Tier'
                    : currentTier === 'team'
                    ? 'Engineering Team Active'
                    : currentTier === 'pro'
                    ? 'Pro Developer Active'
                    : 'Community Starter Plan'}
                </h3>
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200 dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-400/30">
                  {subInfo?.free_beta_mode ? '100% FREE BETA' : currentTier.toUpperCase()}
                </span>
              </div>
              <p className="text-xs text-slate-600 dark:text-neutral-300 mt-0.5 leading-relaxed">
                {subInfo?.free_beta_mode
                  ? 'Pro capabilities are unlocked for free during our public launch. Support hosting or pre-upgrade via Direct UPI below.'
                  : 'Upgrade, renew, or support ongoing GSoC infrastructure with Direct UPI (0% payment gateway fees).'}
              </p>
            </div>
          </div>
        </div>
      )}

      {message && (
        <div
          className={`p-4 rounded-xl border text-xs font-medium flex items-center justify-between ${
            message.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-500/10 dark:border-emerald-500/20 dark:text-emerald-300'
              : 'bg-rose-50 border-rose-200 text-rose-800 dark:bg-rose-500/10 dark:border-rose-500/20 dark:text-rose-300'
          }`}
        >
          <span>{message.text}</span>
          <button onClick={() => setMessage(null)} className="underline ml-4 hover:opacity-80">
            Dismiss
          </button>
        </div>
      )}

      {/* Monthly Task Meter & Active Tier Snapshot */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 relative overflow-hidden shadow-sm dark:shadow-xl">
          <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-neutral-400 font-semibold mb-1">
            Current Tier
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xl font-bold text-slate-900 dark:text-white capitalize">
              {currentTier === 'starter'
                ? 'Community Starter'
                : currentTier === 'pro'
                ? 'Pro Developer'
                : 'Engineering Team'}
            </span>
            <span
              className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${
                currentTier === 'pro'
                  ? 'bg-indigo-50 border-indigo-200 text-indigo-700 dark:bg-indigo-500/20 dark:border-indigo-500/30 dark:text-indigo-300'
                  : currentTier === 'team'
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-700 dark:bg-emerald-500/20 dark:border-emerald-500/30 dark:text-emerald-300'
                  : 'bg-slate-100 border-slate-200 text-slate-700 dark:bg-white/5 dark:border-white/10 dark:text-neutral-300'
              }`}
            >
              {subInfo?.status || 'Active'}
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-neutral-400 mt-2">
            {currentTier === 'starter'
              ? 'Free tier for personal GSoC open-source issue exploration.'
              : 'Full access to unconstrained PR publication and priority queues.'}
          </p>
        </div>

        <div className="md:col-span-2 p-5 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 shadow-sm dark:shadow-xl">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs uppercase tracking-wider text-slate-500 dark:text-neutral-400 font-semibold">
              {isUnlimited ? 'Task Usage' : 'Free Task Credits'}
            </div>
            <span className="text-xs font-mono font-bold text-slate-900 dark:text-white">
              {isUnlimited ? `${usageCount} tasks created (Unlimited)` : `${usageCount} / ${limitCount} credits used`}
            </span>
          </div>

          <div className="w-full bg-slate-100 dark:bg-[#05080f] h-2.5 rounded-full overflow-hidden border border-slate-200 dark:border-white/10 mb-2">
            <div
              className={`h-full transition-all duration-500 ${
                isUnlimited
                  ? 'bg-blue-600 dark:bg-indigo-500 w-full'
                  : usagePct >= 100
                  ? 'bg-rose-500'
                  : usagePct >= 80
                  ? 'bg-amber-500'
                  : 'bg-emerald-500'
              }`}
              style={{ width: isUnlimited ? '100%' : `${usagePct}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-neutral-400">
            <span>{isUnlimited ? 'Unlimited tasks on active tier' : 'One-time 5 free credits (does not reset monthly)'}</span>
            {!isUnlimited && usagePct >= 80 && (
              <span className="text-amber-500 font-medium">
                {limitCount - usageCount <= 0 ? 'All credits used' : `${limitCount - usageCount} credits remaining`}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Inline Active Direct UPI Payment Card (when plan upgrade or Support is selected) */}
      <div ref={upiPanelRef}>
        {activeUpiPanel && (
          <div className="animate-fade-in">
            <UpiPaymentCard
              mode={activeUpiPanel.mode}
              upiConfig={upiConfig}
              planTier={activeUpiPanel.mode === 'plan' ? activeUpiPanel.planTier : undefined}
              billingCycle={activeUpiPanel.mode === 'plan' ? activeUpiPanel.billingCycle : 'monthly'}
              fixedAmountInr={activeUpiPanel.mode === 'plan' ? activeUpiPanel.amountInr : undefined}
              planLabel={activeUpiPanel.mode === 'plan' ? activeUpiPanel.planLabel : undefined}
              onSubmitted={handleUpiSubmitted}
              onCancel={() => setActiveUpiPanel(null)}
            />
          </div>
        )}
      </div>

      {/* Pricing Toggle (Monthly vs Annual) */}
      <div className="flex flex-col items-center justify-center gap-2 pt-2">
        <div className="inline-flex items-center bg-slate-100 dark:bg-[#0c101a] p-1 rounded-xl border border-slate-200 dark:border-white/10 shadow-sm">
          <button
            onClick={() => setBillingCycle('monthly')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition ${
              billingCycle === 'monthly'
                ? 'bg-white text-blue-600 shadow-sm border border-slate-200/80 dark:bg-white dark:text-black dark:border-transparent font-semibold'
                : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white'
            }`}
          >
            Monthly Billing
          </button>
          <button
            onClick={() => setBillingCycle('annual')}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold transition ${
              billingCycle === 'annual'
                ? 'bg-white text-blue-600 shadow-sm border border-slate-200/80 dark:bg-white dark:text-black dark:border-transparent font-semibold'
                : 'text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white'
            }`}
          >
            <span>Annual Billing</span>
            <span className="text-[10px] font-bold text-emerald-500 dark:text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded-full border border-emerald-500/20">
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
          const price = billingCycle === 'annual' ? plan.price_annual : plan.price_monthly;
          const billingSuffix =
            plan.price_monthly === 0 ? 'forever' : billingCycle === 'annual' ? '/ year' : '/ month';

          return (
            <div
              key={plan.id}
              className={`relative flex flex-col justify-between p-6 sm:p-7 rounded-2xl bg-white dark:bg-[#0c101a] border transition-all duration-200 shadow-sm dark:shadow-xl ${
                isPro
                  ? 'border-blue-400 dark:border-indigo-500/50 shadow-blue-500/5 dark:shadow-indigo-500/10 ring-1 ring-blue-400/40 dark:ring-indigo-500/30'
                  : 'border-slate-200 dark:border-white/10 hover:border-slate-300 dark:hover:border-white/20'
              }`}
            >
              {isPro && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-bold text-[10px] tracking-wide uppercase shadow-md">
                  {subInfo?.free_beta_mode
                    ? 'Unlocked in Public Beta'
                    : subInfo?.trial_active
                    ? `${subInfo.trial_days_remaining ?? 15}-Day Free Trial`
                    : 'Most Popular'}
                </div>
              )}

              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">{plan.name}</h3>
                  {isCurrent && (
                    <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200 dark:text-emerald-400 dark:bg-emerald-500/10 dark:border-emerald-500/20">
                      Active
                    </span>
                  )}
                </div>

                <p className="text-xs text-slate-500 dark:text-neutral-400 leading-relaxed min-h-[36px] mb-6">
                  {plan.description}
                </p>

                <div className="flex items-baseline gap-1 mb-6">
                  <span className="text-3xl font-extrabold text-slate-900 dark:text-white">
                    {plan.currency_symbol || '₹'}
                    {price}
                  </span>
                  <span className="text-xs text-slate-500 dark:text-neutral-400 font-medium">{billingSuffix}</span>
                </div>

                <div className="border-t border-slate-100 dark:border-white/10 pt-5 space-y-3 mb-6">
                  {plan.features.map((f, i) => (
                    <div key={i} className="flex items-start gap-2.5 text-xs">
                      {f.included ? (
                        <Check
                          className={`w-4 h-4 shrink-0 mt-0.5 ${
                            f.highlight ? 'text-blue-600 dark:text-indigo-400' : 'text-emerald-600 dark:text-emerald-400'
                          }`}
                        />
                      ) : (
                        <span className="w-4 h-4 shrink-0 text-center text-slate-400 dark:text-neutral-600 font-bold">
                          —
                        </span>
                      )}
                      <span
                        className={
                          f.included
                            ? f.highlight
                              ? 'text-slate-900 dark:text-white font-semibold'
                              : 'text-slate-700 dark:text-neutral-300'
                            : 'text-slate-400 dark:text-neutral-500'
                        }
                      >
                        {f.name}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                {isCurrent ? (
                  <button
                    type="button"
                    disabled
                    className="w-full py-2.5 px-4 rounded-xl bg-blue-50 border border-blue-200 text-blue-700 dark:bg-white/5 dark:border-white/10 dark:text-neutral-400 text-xs font-bold cursor-default"
                  >
                    {isPro && subInfo?.trial_active
                      ? `✓ Active (${subInfo.trial_days_remaining ?? 15}d Trial)`
                      : '✓ Current Active Plan'}
                  </button>
                ) : plan.id === 'starter' ? (
                  <button
                    type="button"
                    disabled
                    className="w-full py-2.5 px-4 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 text-slate-500 dark:bg-white/5 dark:text-neutral-400 text-xs font-semibold cursor-default"
                  >
                    Included in Your Plan
                  </button>
                ) : (
                  <button
                    onClick={() => openUpiCheckout(plan)}
                    disabled={actionLoading !== null}
                    className={`w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-bold transition active:scale-95 shadow-md ${
                      isPro
                        ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-600/20 dark:bg-white dark:text-black dark:hover:bg-neutral-200'
                        : 'bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-200 dark:bg-white/10 dark:hover:bg-white/15 dark:text-white dark:border-white/20'
                    }`}
                  >
                    <QrCode className="w-3.5 h-3.5" />
                    <span>Pay ₹{price} via UPI</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Voluntary Support / Tip Banner */}
      {activeUpiPanel?.mode !== 'support' && (
        <div className="p-5 rounded-2xl bg-gradient-to-r from-amber-50/90 via-orange-50/70 to-rose-50/50 dark:from-amber-950/35 dark:via-orange-950/25 dark:to-rose-950/20 border border-amber-300/80 dark:border-amber-500/35 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm shadow-amber-500/10">
          <div className="flex items-start sm:items-center gap-3.5">
            <div className="p-2.5 rounded-xl bg-gradient-to-br from-amber-500 via-orange-500 to-rose-500 text-white shrink-0 shadow-md shadow-orange-500/25">
              <Heart className="w-5 h-5 fill-white" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  Did this GSoC tracker help you find an issue or land a PR?
                </h3>
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-400/35">
                  ₹49+ • 0% FEE
                </span>
              </div>
              <p className="text-xs text-slate-600 dark:text-neutral-300 mt-0.5">
                Fuel server & GitHub API hosting with a quick 10-second UPI tip to <span className="font-mono font-semibold text-amber-800 dark:text-amber-300">{upiConfig?.upi_vpa || '8116710520@ibl'}</span>.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={openSupportPanel}
            className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 via-orange-500 to-rose-500 hover:from-amber-400 hover:via-orange-400 hover:to-rose-400 text-white text-xs font-bold flex items-center justify-center gap-2 shadow-md shadow-orange-500/25 transition active:scale-95 shrink-0"
          >
            <QrCode className="w-4 h-4" />
            <span>Open Support UPI QR</span>
          </button>
        </div>
      )}

      {/* User's UPI Payment Submissions History */}
      {myUpiRequests.length > 0 && (
        <div className="p-5 sm:p-6 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 shadow-sm dark:shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">Your UPI Payment Submissions</h3>
            </div>
            <span className="text-[11px] font-mono text-slate-500 dark:text-neutral-400">
              {myUpiRequests.length} {myUpiRequests.length === 1 ? 'record' : 'records'}
            </span>
          </div>

          <div className="divide-y divide-slate-100 dark:divide-white/10">
            {myUpiRequests.map((req) => (
              <div key={req.id} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-bold text-slate-900 dark:text-white">
                      ₹{req.amount_inr} •{' '}
                      {req.payment_purpose === 'plan'
                        ? `${(req.plan_tier || 'pro').toUpperCase()} Plan (${req.billing_cycle})`
                        : 'Developer Support / Tip'}
                    </span>
                    <span
                      className={`text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded-full border ${
                        STATUS_BADGE_MAP[req.status] || STATUS_BADGE_MAP.pending
                      }`}
                    >
                      {req.status}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-neutral-400 font-mono">
                    UTR: {req.utr_number}
                    {req.created_at ? ` • ${new Date(req.created_at).toLocaleString()}` : ''}
                  </div>
                  {req.admin_note && (
                    <div className="text-[11px] text-slate-600 dark:text-neutral-300">Note: {req.admin_note}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Admin Verification Queue (Only visible to platform owner / superuser) */}
      {subInfo?.is_admin && (
        <div className="p-5 sm:p-6 rounded-2xl bg-white dark:bg-[#0c101a] border border-blue-200 dark:border-blue-500/30 shadow-sm dark:shadow-xl space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 dark:border-white/10 pb-4">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-400 border border-blue-200 dark:border-blue-500/30">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    Admin: UPI Payment Verification Queue
                  </h3>
                  {(subInfo.pending_admin_upi_count ?? 0) > 0 && (
                    <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-500/30">
                      {subInfo.pending_admin_upi_count} pending
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 dark:text-neutral-400">
                  Match UTR IDs in your PhonePe app ({upiConfig?.upi_vpa || '8116710520@ibl'}) and approve to unlock user plans.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1.5 flex-wrap">
              {(['pending', 'approved', 'rejected', 'all'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => handleAdminFilterChange(tab)}
                  className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold capitalize transition ${
                    adminFilter === tab
                      ? 'bg-blue-600 text-white shadow-xs'
                      : 'bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-white/5 dark:hover:bg-white/10 dark:text-neutral-300'
                  }`}
                >
                  {tab}
                </button>
              ))}
              <button
                type="button"
                onClick={() => handleAdminFilterChange(adminFilter)}
                disabled={actionLoading === 'admin_refresh'}
                className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 dark:bg-white/5 dark:hover:bg-white/10 dark:text-neutral-300 transition"
                title="Refresh queue"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${actionLoading === 'admin_refresh' ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {adminUpiRequests.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-500 dark:text-neutral-400">
              No {adminFilter === 'all' ? '' : adminFilter} UPI submissions right now.
            </div>
          ) : (
            <div className="space-y-3">
              {adminUpiRequests.map((req) => (
                <div
                  key={req.id}
                  className="p-4 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                >
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-extrabold text-slate-900 dark:text-white font-mono">
                        ₹{req.amount_inr}
                      </span>
                      <span className="text-xs font-bold text-slate-800 dark:text-neutral-200">
                        {req.payment_purpose === 'plan'
                          ? `${(req.plan_tier || 'pro').toUpperCase()} Plan (${req.billing_cycle})`
                          : 'Voluntary Support'}
                      </span>
                      <span
                        className={`text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded-full border ${
                          STATUS_BADGE_MAP[req.status] || STATUS_BADGE_MAP.pending
                        }`}
                      >
                        {req.status}
                      </span>
                    </div>
                    <div className="text-xs text-slate-600 dark:text-neutral-300">
                      User: <strong>{req.payer_username || 'Unknown'}</strong>
                      {req.payer_email ? ` (${req.payer_email})` : ''}
                      {req.payer_upi_id ? ` • Sender VPA: ${req.payer_upi_id}` : ''}
                    </div>
                    <div className="text-[11px] font-mono text-slate-500 dark:text-neutral-400">
                      UTR: <strong className="text-slate-800 dark:text-neutral-200">{req.utr_number}</strong>
                      {req.created_at ? ` • ${new Date(req.created_at).toLocaleString()}` : ''}
                    </div>
                    {req.note && (
                      <div className="text-[11px] text-slate-500 dark:text-neutral-400 italic">"{req.note}"</div>
                    )}
                  </div>

                  {req.status === 'pending' && (
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => handleAdminReview(req.id, 'approve')}
                        disabled={actionLoading !== null}
                        className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-sm transition active:scale-95 disabled:opacity-50"
                      >
                        {actionLoading === `review_${req.id}_approve` ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Check className="w-3.5 h-3.5" />
                        )}
                        <span>Approve{req.payment_purpose === 'plan' ? ' & Activate' : ''}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleAdminReview(req.id, 'reject')}
                        disabled={actionLoading !== null}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 dark:bg-rose-500/10 dark:hover:bg-rose-500/20 dark:border-rose-500/30 dark:text-rose-300 text-xs font-bold transition active:scale-95 disabled:opacity-50"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        <span>Reject</span>
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Developer Simulation Mode Box (Admin only) */}
      {subInfo?.is_admin && (
      <div className="p-5 rounded-2xl bg-white dark:bg-[#0c101a] border border-dashed border-slate-300 dark:border-white/20 shadow-sm dark:shadow-xl">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <span className="p-1 rounded bg-amber-50 text-amber-600 border border-amber-200 dark:bg-amber-500/20 dark:text-amber-400 dark:border-transparent">
              <Zap className="w-4 h-4" />
            </span>
            <span className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Developer Quick Simulation Switcher
            </span>
            <span className="text-[10px] text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200 dark:text-amber-400 dark:bg-amber-500/10 dark:border-amber-500/20 font-semibold">
              Test Mode
            </span>
          </div>
          <span className="text-[11px] text-slate-500 dark:text-neutral-400">
            Instantly toggle organization tiers to verify quota enforcement & UI changes.
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => handleSimulateTier('starter')}
            disabled={actionLoading !== null || currentTier === 'starter'}
            className="px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-xs font-semibold text-slate-700 dark:bg-white/5 dark:hover:bg-white/10 dark:border-white/10 dark:text-neutral-200 transition disabled:opacity-40"
          >
            Switch to Starter (5 one-time credits)
          </button>
          <button
            onClick={() => handleSimulateTier('pro')}
            disabled={actionLoading !== null || currentTier === 'pro'}
            className="px-3 py-1.5 rounded-xl bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-xs font-semibold text-indigo-700 dark:bg-indigo-950/60 dark:hover:bg-indigo-900/60 dark:border-indigo-500/30 dark:text-indigo-200 transition disabled:opacity-40"
          >
            Switch to Pro (Unlimited)
          </button>
          <button
            onClick={() => handleSimulateTier('team')}
            disabled={actionLoading !== null || currentTier === 'team'}
            className="px-3 py-1.5 rounded-xl bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/60 dark:hover:bg-emerald-900/60 dark:border-emerald-500/30 dark:text-emerald-200 transition disabled:opacity-40"
          >
            Switch to Team (Private & RBAC)
          </button>
        </div>
      </div>
      )}
    </div>
  );
}
