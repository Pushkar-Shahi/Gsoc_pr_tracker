import React, { useEffect, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { UpiConfig, UpiPaymentRequest } from '../types';
import { useLockBodyScroll } from '../hooks/useLockBodyScroll';
import * as api from '../api';
import { UpiPaymentCard } from './UpiPaymentCard';

interface SupportUpiModalProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigateToBilling?: () => void;
  onPaymentSubmitted?: (req: UpiPaymentRequest) => void;
}

export const SupportUpiModal: React.FC<SupportUpiModalProps> = ({
  isOpen,
  onClose,
  onNavigateToBilling,
  onPaymentSubmitted,
}) => {
  const [upiConfig, setUpiConfig] = useState<UpiConfig | null>(null);

  useLockBodyScroll(isOpen);

  useEffect(() => {
    if (!isOpen) return;
    api.fetchUpiConfig().then(setUpiConfig).catch(() => null);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/65 dark:bg-black/80 backdrop-blur-xs animate-fade-in overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl my-auto rounded-2xl shadow-2xl animate-scale-up"
        onClick={(e) => e.stopPropagation()}
      >
        <UpiPaymentCard
          mode="support"
          upiConfig={upiConfig}
          onCancel={onClose}
          onSubmitted={(req) => {
            window.dispatchEvent(new CustomEvent('issuetopr-upi-updated'));
            if (onPaymentSubmitted) onPaymentSubmitted(req);
          }}
        />

        {onNavigateToBilling && (
          <div className="mt-2.5 flex justify-end">
            <button
              type="button"
              onClick={() => {
                onClose();
                onNavigateToBilling();
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white/95 dark:bg-[#0c101a] border border-slate-200 dark:border-white/15 text-xs font-semibold text-slate-700 dark:text-neutral-200 hover:bg-slate-100 dark:hover:bg-white/10 shadow-lg transition"
            >
              <span>View Plans, Payment History & Billing</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
