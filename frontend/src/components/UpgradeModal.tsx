import React, { useState } from 'react';
import { Sparkles, Check, ArrowRight, X, ShieldAlert, Loader2 } from 'lucide-react';
import { createCheckoutSession } from '../api';

interface UpgradeModalProps {
  isOpen: boolean;
  onClose: () => void;
  reason?: string;
  onNavigateToBilling?: () => void;
}

export function UpgradeModal({
  isOpen,
  onClose,
  reason,
  onNavigateToBilling
}: UpgradeModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleQuickUpgrade = async () => {
    setLoading(true);
    setError(null);
    try {
      const session = await createCheckoutSession('pro', 'monthly');
      if (session.checkout_url) {
        window.location.href = session.checkout_url;
      }
    } catch (err: any) {
      setError(err.message || 'Failed to initialize checkout');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="relative w-full max-w-lg overflow-hidden bg-neutral-950 border border-white/10 rounded-2xl shadow-2xl p-6 sm:p-8"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Glow ambient background */}
        <div className="absolute -top-24 -left-24 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

        <button 
          onClick={onClose}
          className="absolute top-4 right-4 p-2 text-neutral-400 hover:text-white rounded-lg hover:bg-neutral-900 transition"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="p-3 bg-gradient-to-br from-amber-500/20 to-orange-500/20 border border-amber-500/30 rounded-xl text-amber-400">
            <Sparkles className="w-6 h-6" />
          </div>
          <div>
            <span className="text-[11px] font-semibold tracking-wider uppercase text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-500/20">
              Pro Entitlement Required
            </span>
            <h2 className="text-xl font-bold text-white mt-1">
              Unlock Unlimited Tasks with Pro
            </h2>
          </div>
        </div>

        <p className="text-sm text-neutral-300 leading-relaxed mb-6">
          {reason || "You have reached your free tier limit of 5 tasks for this month. Upgrade to Pro for unconstrained PR generation, priority runners, and bounty filters."}
        </p>

        <div className="bg-neutral-900/60 border border-white/5 rounded-xl p-4 mb-6 space-y-2.5">
          <div className="flex items-start gap-2.5 text-xs text-neutral-200">
            <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span><strong>Unlimited tasks & PR publications</strong> each month</span>
          </div>
          <div className="flex items-start gap-2.5 text-xs text-neutral-200">
            <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span><strong>Real-time webhook discovery</strong> & Algora/Polar bounty tracker</span>
          </div>
          <div className="flex items-start gap-2.5 text-xs text-neutral-200">
            <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span><strong>Priority runner scheduling</strong> & multi-repo sync matrix</span>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 mb-4 text-xs text-rose-300 bg-rose-500/10 border border-rose-500/20 rounded-xl">
            <ShieldAlert className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex flex-col sm:flex-row items-center gap-3">
          <button
            onClick={handleQuickUpgrade}
            disabled={loading}
            className="w-full sm:flex-1 flex items-center justify-center gap-2 py-3 px-5 rounded-xl bg-white text-black font-bold text-sm hover:bg-neutral-200 active:scale-95 transition shadow-lg shadow-white/5 disabled:opacity-50"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Redirecting...</span>
              </>
            ) : (
              <>
                <span>Upgrade to Pro ($29/mo)</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>

          {onNavigateToBilling && (
            <button
              onClick={() => {
                onClose();
                onNavigateToBilling();
              }}
              className="w-full sm:w-auto py-3 px-4 rounded-xl border border-white/10 hover:bg-neutral-900 text-xs font-semibold text-neutral-300 transition"
            >
              Compare All Plans
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
