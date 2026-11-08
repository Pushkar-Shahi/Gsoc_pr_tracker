import React from 'react';
import { Sparkles, Check, ArrowRight, X } from 'lucide-react';

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
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 dark:bg-black/80 backdrop-blur-xs animate-fade-in">
      <div 
        className="relative w-full max-w-lg overflow-hidden bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl shadow-2xl p-6 sm:p-8 animate-scale-up"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Glow ambient background */}
        <div className="absolute -top-24 -left-24 w-48 h-48 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

        <button 
          onClick={onClose}
          className="absolute top-4 right-4 p-2 text-slate-400 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white rounded-lg hover:bg-slate-100 dark:hover:bg-white/10 transition"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="p-3 bg-blue-50 dark:bg-blue-500/20 border border-blue-200 dark:border-blue-500/30 rounded-xl text-blue-600 dark:text-blue-400">
            <Sparkles className="w-6 h-6" />
          </div>
          <div>
            <span className="text-[11px] font-semibold tracking-wider uppercase text-blue-700 bg-blue-50 px-2.5 py-0.5 rounded-full border border-blue-200 dark:text-blue-400 dark:bg-blue-500/10 dark:border-blue-500/20">
              Public Launch Special
            </span>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              Early Access Beta: All Features Free
            </h2>
          </div>
        </div>

        <p className="text-sm text-slate-600 dark:text-neutral-300 leading-relaxed mb-6">
          {reason || "You have full, unrestricted access to all Pro developer capabilities completely free during our public launch. Build, discover issues, and ship pull requests without quotas!"}
        </p>

        <div className="bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl p-4 mb-6 space-y-2.5">
          <div className="flex items-start gap-2.5 text-xs text-slate-800 dark:text-neutral-200">
            <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
            <span><strong>Unlimited tasks & PR publications</strong> each month</span>
          </div>
          <div className="flex items-start gap-2.5 text-xs text-slate-800 dark:text-neutral-200">
            <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
            <span><strong>Real-time webhook discovery</strong> & GSoC organization issue tracking</span>
          </div>
          <div className="flex items-start gap-2.5 text-xs text-slate-800 dark:text-neutral-200">
            <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
            <span><strong>Priority runner scheduling</strong> & secret diff scanning</span>
          </div>
          <div className="flex items-start gap-2.5 text-xs text-slate-800 dark:text-neutral-200">
            <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
            <span><strong>Founder Early Adopter Status</strong> grandfathered for life</span>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3">
          <button
            onClick={onClose}
            className="w-full sm:flex-1 flex items-center justify-center gap-2 py-3 px-5 rounded-xl bg-blue-600 text-white font-bold text-sm hover:bg-blue-500 active:scale-95 transition shadow-md shadow-blue-600/20"
          >
            <span>Start Building (100% Free)</span>
            <ArrowRight className="w-4 h-4" />
          </button>

          {onNavigateToBilling && (
            <button
              onClick={() => {
                onClose();
                onNavigateToBilling();
              }}
              className="w-full sm:w-auto py-3 px-4 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-white/10 text-xs font-semibold text-slate-700 dark:text-neutral-300 transition"
            >
              View Upcoming Plans
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

