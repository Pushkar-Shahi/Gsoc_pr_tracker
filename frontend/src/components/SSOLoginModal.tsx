import React, { useState } from 'react';
import { Building2, Shield, ArrowRight, CheckCircle2, AlertCircle, Sparkles, X, Loader2 } from 'lucide-react';
import { lookupSSODomain, loginWithSSO, SSOLookupResult } from '../api';

interface SSOLoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const SSOLoginModal: React.FC<SSOLoginModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const [emailOrDomain, setEmailOrDomain] = useState('');
  const [lookupResult, setLookupResult] = useState<SSOLookupResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signingIn, setSigningIn] = useState(false);

  if (!isOpen) return null;

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    const val = emailOrDomain.trim();
    if (!val) {
      setError('Please enter your work email or company domain.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setLookupResult(null);

      const res = await lookupSSODomain(val);
      setLookupResult(res);

      // If configured and ready, we can proceed to sign-in
      if (res.configured) {
        await executeSSOLogin(val, res);
      }
    } catch (err: any) {
      setError(err.message || 'Domain lookup failed.');
    } finally {
      setLoading(false);
    }
  };

  const executeSSOLogin = async (emailInput: string, lookup: SSOLookupResult) => {
    try {
      setSigningIn(true);
      setError(null);

      const email = emailInput.includes('@') ? emailInput : `user@${emailInput}`;
      await loginWithSSO({
        email,
        organization_slug: lookup.organization_slug,
        provider: lookup.provider || 'saml',
        demo_mode: Boolean(lookup.demo_available)
      });

      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Enterprise SSO login failed.');
    } finally {
      setSigningIn(false);
    }
  };

  const handleDemoSSO = async () => {
    try {
      setSigningIn(true);
      setError(null);
      setEmailOrDomain('sarah.lead@acme.corp');

      await loginWithSSO({
        email: 'sarah.lead@acme.corp',
        organization_slug: 'acme-corp',
        provider: 'okta',
        demo_mode: true
      });

      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Demo SSO sign-in failed.');
    } finally {
      setSigningIn(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 dark:bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-[420px] rounded-2xl bg-white dark:bg-[#111111] border border-slate-200 dark:border-neutral-800 p-6 sm:p-7 shadow-2xl space-y-6">
        
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-slate-400 hover:text-slate-600 dark:text-neutral-500 dark:hover:text-neutral-200 p-1.5 rounded-lg transition"
          aria-label="Close"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Modal Header */}
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-neutral-800/80 border border-slate-200 dark:border-neutral-700 flex items-center justify-center text-slate-800 dark:text-neutral-100 shadow-sm">
            <Building2 className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-xl font-bold tracking-tight text-slate-950 dark:text-white">
              Enterprise Single Sign-On
            </h3>
            <p className="text-xs text-slate-500 dark:text-neutral-400 mt-1 max-w-[280px]">
              Sign in with your organization's corporate Identity Provider (Okta, Azure AD, SAML 2.0).
            </p>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 text-xs flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span className="leading-tight">{error}</span>
          </div>
        )}

        {/* Unconfigured Domain Alert */}
        {lookupResult && !lookupResult.configured && (
          <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-300 text-xs space-y-1">
            <div className="font-semibold flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5" />
              <span>SSO Not Configured</span>
            </div>
            <p className="text-[11px] opacity-90 leading-relaxed">
              {lookupResult.message || `No active SSO configuration found for "${lookupResult.domain}".`}
            </p>
          </div>
        )}

        {/* Email / Domain Form */}
        <form onSubmit={handleLookup} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-neutral-300 mb-1.5">
              Work email or company domain
            </label>
            <input
              type="text"
              required
              value={emailOrDomain}
              onChange={(e) => {
                setEmailOrDomain(e.target.value);
                setLookupResult(null);
                setError(null);
              }}
              placeholder="name@company.com or company.corp"
              className="w-full h-11 px-3.5 rounded-xl border border-slate-200 dark:border-neutral-800 bg-white dark:bg-[#0a0a0a] text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-neutral-600 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-white transition text-sm font-sans"
            />
          </div>

          <button
            type="submit"
            disabled={loading || signingIn || !emailOrDomain.trim()}
            className="w-full h-11 rounded-xl font-semibold text-sm transition-all duration-200 bg-slate-950 text-white hover:bg-slate-800 dark:bg-white dark:text-black dark:hover:bg-neutral-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 cursor-pointer"
          >
            {loading || signingIn ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{signingIn ? 'Authenticating with IdP...' : 'Checking Identity Provider...'}</span>
              </>
            ) : (
              <>
                <span>Continue with SSO</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        {/* Interactive Enterprise SSO Test / Demo Card */}
        <div className="pt-2 border-t border-slate-100 dark:border-neutral-800/80">
          <div className="p-3 rounded-xl bg-slate-50 dark:bg-neutral-900/60 border border-slate-200/70 dark:border-neutral-800 flex items-center justify-between gap-3">
            <div className="space-y-0.5">
              <div className="flex items-center gap-1.5 text-xs font-bold text-slate-900 dark:text-white">
                <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                <span>Test Enterprise SSO</span>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-neutral-400">
                Acme Corp · Okta SAML 2.0 Demo
              </p>
            </div>
            <button
              type="button"
              onClick={handleDemoSSO}
              disabled={signingIn || loading}
              className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition active:scale-95 disabled:opacity-50 cursor-pointer"
            >
              Sign In &rarr;
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};

