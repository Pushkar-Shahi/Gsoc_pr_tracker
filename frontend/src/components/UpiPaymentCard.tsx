import React, { useMemo, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import {
  Copy, Check, QrCode,
  ShieldCheck, Info, Loader2, Heart, Sparkles, X
} from 'lucide-react';
import { UpiConfig, UpiPaymentRequest } from '../types';
import * as api from '../api';

interface UpiPaymentCardProps {
  mode: 'plan' | 'support';
  upiConfig?: UpiConfig | null;
  planTier?: 'pro' | 'team';
  billingCycle?: 'monthly' | 'annual';
  fixedAmountInr?: number;
  planLabel?: string;
  onSubmitted?: (req: UpiPaymentRequest) => void;
  onCancel?: () => void;
}

const DEFAULT_SUPPORT_PRESETS = [49, 100, 250, 500];

/**
 * Shared Direct UPI payment widget supporting dynamic amount-locked QRs
 * and UTR submission.
 */
export const UpiPaymentCard: React.FC<UpiPaymentCardProps> = ({
  mode,
  upiConfig,
  planTier,
  billingCycle = 'monthly',
  fixedAmountInr,
  planLabel,
  onSubmitted,
  onCancel,
}) => {
  const presets = upiConfig?.suggested_support_amounts?.length
    ? upiConfig.suggested_support_amounts
    : DEFAULT_SUPPORT_PRESETS;

  const [supportAmount, setSupportAmount] = useState<number>(presets[1] || 100);
  const [customAmountInput, setCustomAmountInput] = useState<string>(String(presets[1] || 100));
  const [copiedVpa, setCopiedVpa] = useState(false);

  // UTR Submission state
  const [utrNumber, setUtrNumber] = useState('');
  const [payerUpiId, setPayerUpiId] = useState('');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submittedRecord, setSubmittedRecord] = useState<UpiPaymentRequest | null>(null);

  const upiVpa = upiConfig?.upi_vpa || '8116710520@ibl';
  const payeeName = upiConfig?.payee_name || 'Pushkar Shahi';

  const effectiveAmount = mode === 'plan' ? (fixedAmountInr ?? 100) : Math.max(1, Number(supportAmount) || 0);

  const transactionNote = useMemo(() => {
    if (mode === 'plan' && planTier) {
      return `GSoC ${planTier.toUpperCase()} ${billingCycle}`;
    }
    return 'Support GSoC Issue-to-PR';
  }, [mode, planTier, billingCycle]);

  const upiUri = useMemo(() => {
    const params = new URLSearchParams({
      pa: upiVpa,
      pn: payeeName,
      am: String(effectiveAmount),
      cu: 'INR',
      tn: transactionNote,
    });
    return `upi://pay?${params.toString()}`;
  }, [upiVpa, payeeName, effectiveAmount, transactionNote]);

  const handleSelectPreset = (amt: number) => {
    setSupportAmount(amt);
    setCustomAmountInput(String(amt));
    setSubmitError(null);
  };

  const handleCustomAmountChange = (val: string) => {
    const cleaned = val.replace(/[^\d]/g, '').slice(0, 5);
    setCustomAmountInput(cleaned);
    const parsed = parseInt(cleaned, 10);
    if (!Number.isNaN(parsed) && parsed > 0) {
      setSupportAmount(parsed);
      if (parsed > 50000) {
        setSubmitError('Maximum UPI payment limit is ₹50,000.');
      } else {
        setSubmitError(null);
      }
    } else if (cleaned === '') {
      setSupportAmount(0);
      setSubmitError(null);
    }
  };

  const handleCopyVpa = async () => {
    try {
      await navigator.clipboard.writeText(upiVpa);
      setCopiedVpa(true);
      setTimeout(() => setCopiedVpa(false), 2000);
    } catch {
      setSubmitError(`Copy manually: ${upiVpa}`);
    }
  };

  const handleSubmitUtr = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    if (effectiveAmount < 1 || effectiveAmount > 50000) {
      setSubmitError('Please choose an amount between ₹1 and ₹50,000.');
      return;
    }

    const cleanedUtr = utrNumber.replace(/\s+/g, '').toUpperCase();
    if (!/^[A-Z0-9]{10,35}$/.test(cleanedUtr)) {
      setSubmitError('Enter a valid 12-digit UTR or UPI Transaction Reference ID (min 10 characters).');
      return;
    }

    setSubmitting(true);
    try {
      const record = await api.submitUpiPayment({
        payment_purpose: mode,
        plan_tier: mode === 'plan' ? planTier : undefined,
        billing_cycle: mode === 'plan' ? billingCycle : 'one_time',
        amount_inr: effectiveAmount,
        utr_number: cleanedUtr,
        payer_upi_id: payerUpiId.trim() || undefined,
        note: note.trim() || undefined,
      });
      setSubmittedRecord(record);
      setUtrNumber('');
      setNote('');
      if (onSubmitted) {
        onSubmitted(record);
      }
    } catch (err: any) {
      setSubmitError(err.message || 'Could not submit UPI reference. Please verify and try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 shadow-sm dark:shadow-xl overflow-hidden">
      {/* Top Banner */}
      <div className={`px-5 py-4 border-b border-slate-200 dark:border-white/10 flex flex-wrap items-center justify-between gap-3 ${
        mode === 'support'
          ? 'bg-gradient-to-r from-amber-50/95 via-orange-50/80 to-rose-50/70 dark:from-amber-950/40 dark:via-orange-950/30 dark:to-rose-950/25'
          : 'bg-gradient-to-r from-emerald-50/90 via-blue-50/70 to-slate-50 dark:from-emerald-950/30 dark:via-blue-950/30 dark:to-[#0c101a]'
      }`}>
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-xl text-white shadow-sm shrink-0 ${
            mode === 'support'
              ? 'bg-gradient-to-br from-amber-500 via-orange-500 to-rose-500 shadow-orange-500/30'
              : 'bg-emerald-600 shadow-emerald-600/20'
          }`}>
            {mode === 'support' ? <Heart className="w-4 h-4 fill-white" /> : <QrCode className="w-4 h-4" />}
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                {mode === 'plan'
                  ? `Pay via UPI — ${planLabel || `${(planTier || 'pro').toUpperCase()} Plan`}`
                  : 'Support GSoC Issue-to-PR via Direct UPI'}
              </h3>
              <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                mode === 'support'
                  ? 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-400/35'
                  : 'bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-500/20 dark:text-emerald-300 dark:border-emerald-400/30'
              }`}>
                0% FEE • DIRECT UPI
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-neutral-300 mt-0.5">
              {mode === 'support'
                ? <>100% funds GSoC server & GitHub API hosting • Pay directly to <span className="font-mono font-semibold text-slate-900 dark:text-white">{upiVpa}</span> ({payeeName}).</>
                : <>Pay directly to <span className="font-mono font-semibold text-slate-900 dark:text-white">{upiVpa}</span> ({payeeName}) via PhonePe, GPay, Paytm, or BHIM.</>}
            </p>
          </div>
        </div>

        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close UPI panel"
            className="p-2 rounded-xl text-slate-500 hover:text-slate-900 dark:text-neutral-400 dark:hover:text-white hover:bg-slate-200/60 dark:hover:bg-white/10 transition shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="p-5 sm:p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left: QR Code, UPI ID Copy & App Deep Link */}
        <div className="lg:col-span-5 flex flex-col items-center text-center space-y-4">
          {/* Amount Selector (Support mode) or Fixed Plan Price Badge */}
          {mode === 'support' ? (
            <div className="w-full space-y-2">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-neutral-400 text-left">
                Choose Support Amount (INR)
              </div>
              <div className="grid grid-cols-4 gap-1.5 pt-1">
                {presets.map((amt, idx) => {
                  const isPopular = amt === 100 || (idx === 1 && !presets.includes(100));
                  const isSelected = supportAmount === amt;
                  return (
                    <button
                      key={amt}
                      type="button"
                      onClick={() => handleSelectPreset(amt)}
                      className={`relative py-2 rounded-xl text-xs font-bold transition active:scale-95 border ${
                        isSelected
                          ? 'bg-gradient-to-r from-amber-500 via-orange-500 to-rose-500 text-white border-amber-400 shadow-md shadow-orange-500/25'
                          : isPopular
                          ? 'bg-amber-50/90 hover:bg-amber-100 text-amber-900 border-amber-300 dark:bg-amber-500/10 dark:hover:bg-amber-500/20 dark:text-amber-200 dark:border-amber-400/40'
                          : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200 dark:bg-white/5 dark:hover:bg-white/10 dark:text-neutral-300 dark:border-white/10'
                      }`}
                    >
                      {isPopular && (
                        <span className="absolute -top-2 left-1/2 -translate-x-1/2 px-1.5 py-0.2 rounded-full bg-amber-500 text-white text-[8px] font-mono font-extrabold tracking-wider uppercase shadow-xs">
                          Popular
                        </span>
                      )}
                      ₹{amt}
                    </button>
                  );
                })}
              </div>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs font-bold text-slate-500 dark:text-neutral-400">
                  ₹
                </span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={customAmountInput}
                  onChange={(e) => handleCustomAmountChange(e.target.value)}
                  placeholder="Custom amount (max ₹50,000)"
                  className="w-full pl-7 pr-3 py-2 rounded-xl text-xs font-semibold bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </div>
            </div>
          ) : (
            <div className="w-full p-3 rounded-xl bg-blue-50/70 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-500/30 flex items-center justify-between">
              <div className="text-left">
                <div className="text-[10px] font-mono uppercase tracking-wider text-blue-700 dark:text-blue-300 font-bold">
                  Amount Due
                </div>
                <div className="text-xs text-slate-600 dark:text-neutral-300">
                  {planLabel || `${(planTier || 'pro').toUpperCase()} (${billingCycle})`}
                </div>
              </div>
              <div className="text-2xl font-extrabold text-slate-900 dark:text-white font-mono">
                ₹{effectiveAmount}
              </div>
            </div>
          )}

          {/* Amount-Locked QR Code Display with crisp high-contrast quiet zone */}
          <div className="flex flex-col items-center space-y-2">
            <div className={`p-3.5 rounded-2xl bg-white border shadow-md inline-block ${
              mode === 'support'
                ? 'border-amber-300 ring-2 ring-amber-400/40 shadow-amber-500/15'
                : 'border-slate-200'
            }`}>
              <QRCodeSVG
                value={upiUri}
                size={176}
                level="M"
                bgColor="#ffffff"
                fgColor="#0f172a"
                includeMargin={false}
              />
            </div>
            <p className="text-[11px] text-slate-500 dark:text-neutral-400">
              Amount-locked to <strong className="text-slate-800 dark:text-neutral-200">₹{effectiveAmount}</strong> • Works on PhonePe, GPay, Paytm, BHIM
            </p>
          </div>

          {/* Copy UPI ID */}
          <div className="w-full">
            <div className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10">
              <div className="text-left min-w-0">
                <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400 dark:text-neutral-500">
                  UPI ID
                </div>
                <div className="text-xs font-mono font-bold text-slate-900 dark:text-white truncate">
                  {upiVpa}
                </div>
              </div>
              <button
                type="button"
                onClick={handleCopyVpa}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white hover:bg-slate-100 border border-slate-200 text-slate-700 dark:bg-white/10 dark:hover:bg-white/15 dark:border-white/10 dark:text-white text-[11px] font-semibold transition active:scale-95 shrink-0"
              >
                {copiedVpa ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-500" />
                    <span className="text-emerald-600 dark:text-emerald-400">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy ID</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Right: Step 2 UTR Submission + AutoPay Info */}
        <div className="lg:col-span-7 space-y-4">
          <div className="p-4 rounded-2xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-500" />
                <span>Step 2: Confirm Payment with UTR / Ref No.</span>
              </h4>
              {mode === 'support' && (
                <span className="text-[10px] text-slate-500 dark:text-neutral-400 font-medium">
                  Optional for tips
                </span>
              )}
            </div>

            <p className="text-xs text-slate-600 dark:text-neutral-400 leading-relaxed">
              {mode === 'plan'
                ? 'After completing your UPI payment, enter the 12-digit UTR / UPI Reference ID from your PhonePe, GPay, or Paytm receipt so we can verify and activate your tier.'
                : 'Thank you for supporting open-source GSoC tooling! After paying via QR or UPI ID, you can optionally log your 12-digit UTR below so your workspace gets a Verified Supporter record.'}
            </p>

            {submittedRecord ? (
              <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 dark:bg-emerald-500/10 dark:border-emerald-500/25 space-y-2">
                <div className="flex items-center gap-2 text-emerald-800 dark:text-emerald-300 font-bold text-xs">
                  <Sparkles className="w-4 h-4 shrink-0" />
                  <span>Payment Reference Submitted — Pending Verification</span>
                </div>
                <div className="text-xs text-emerald-700 dark:text-emerald-200/90 space-y-1">
                  <div>
                    UTR: <span className="font-mono font-bold">{submittedRecord.utr_number}</span> • Amount:{' '}
                    <strong>₹{submittedRecord.amount_inr}</strong>
                  </div>
                  <p className="text-[11px] opacity-90">
                    Your submission is queued for verification. Once approved, your account status updates automatically.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSubmittedRecord(null)}
                  className="text-[11px] font-semibold text-emerald-700 dark:text-emerald-300 underline hover:opacity-80"
                >
                  Submit another payment reference
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmitUtr} className="space-y-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-700 dark:text-neutral-300 mb-1">
                    12-Digit UTR / UPI Transaction Reference ID <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={utrNumber}
                    onChange={(e) => setUtrNumber(e.target.value)}
                    placeholder="e.g. 431298765432"
                    className="w-full px-3.5 py-2.5 rounded-xl text-xs font-mono bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/15 text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-700 dark:text-neutral-300 mb-1">
                      Your UPI ID <span className="text-slate-400 font-normal">(optional)</span>
                    </label>
                    <input
                      type="text"
                      value={payerUpiId}
                      onChange={(e) => setPayerUpiId(e.target.value)}
                      placeholder="yourname@okaxis"
                      className="w-full px-3 py-2 rounded-xl text-xs bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/15 text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-700 dark:text-neutral-300 mb-1">
                      Note / GitHub Handle <span className="text-slate-400 font-normal">(optional)</span>
                    </label>
                    <input
                      type="text"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="Message or GitHub ID"
                      className="w-full px-3 py-2 rounded-xl text-xs bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/15 text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                    />
                  </div>
                </div>

                {submitError && (
                  <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 dark:bg-rose-500/10 dark:border-rose-500/20 dark:text-rose-300 text-xs">
                    {submitError}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={submitting || effectiveAmount < 1}
                  className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-sm shadow-emerald-600/20 transition active:scale-95 disabled:opacity-50"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Submitting Reference...</span>
                    </>
                  ) : (
                    <>
                      <Check className="w-4 h-4" />
                      <span>
                        {mode === 'plan'
                          ? `Submit ₹${effectiveAmount} Payment Reference for Approval`
                          : `Record ₹${effectiveAmount} Support Payment`}
                      </span>
                    </>
                  )}
                </button>
              </form>
            )}
          </div>

          {/* Honest AutoPay Roadmap Info Box */}
          <div className="p-3.5 rounded-xl bg-amber-50/70 dark:bg-amber-950/20 border border-amber-200/80 dark:border-amber-500/25 flex items-start gap-2.5">
            <Info className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div className="text-[11px] text-amber-900/90 dark:text-amber-200/85 leading-relaxed">
              <span className="font-bold">About UPI AutoPay:</span>{' '}
              {upiConfig?.autopay_note ||
                'Direct personal UPI supports instant 0%-fee one-time transfers. Automated monthly UPI AutoPay mandates require a merchant payment gateway (coming soon).'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
