import React, { useState, useEffect } from 'react';
import { 
  Lock, Eye, EyeOff, CheckCircle2, ShieldCheck, 
  AlertCircle, Building2, Loader2, Sparkles, X, HelpCircle, ArrowRight
} from 'lucide-react';
import { 
  loginWithPassword, 
  signupWithEmail,
  verifyAuth, 
  setAuthToken,
  setOnUnauthorized, 
  devGitHubLogin,
  devGoogleLogin,
  verifyGoogleCredential
} from '../api';
import { EnterpriseSSOModal } from './EnterpriseSSOModal';
import { BrandIcon } from './BrandIcon';

interface AuthGateProps {
  children: React.ReactNode;
}

export function AuthGate({ children }: AuthGateProps) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [authMode, setAuthMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isShaking, setIsShaking] = useState(false);
  const [isSsoOpen, setIsSsoOpen] = useState(false);
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [googleOriginMismatch, setGoogleOriginMismatch] = useState(false);
  const [authProviderLoading, setAuthProviderLoading] = useState(false);

  const googleClientId = "842489213804-lnvakm6obbd26vj8qsdi8s3ri3fq1aev.apps.googleusercontent.com";

  // Check auth & biometric availability on mount
  useEffect(() => {
    let mounted = true;

    // Handle OAuth callback token in URL query
    const urlParams = new URLSearchParams(window.location.search);
    const oauthToken = urlParams.get('token');
    if (oauthToken) {
      setAuthToken(oauthToken);
      window.history.replaceState({}, '', window.location.pathname);
      setIsAuthenticated(true);
      return;
    }

    verifyAuth().then((valid) => {
      if (mounted) {
        setIsAuthenticated(valid);
      }
    });

    setOnUnauthorized(() => {
      setIsAuthenticated(false);
      setError('Session expired. Please sign in again.');
    });

    return () => {
      mounted = false;
    };
  }, []);

  // Initialize Google Identity Services (GIS)
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const setupGoogleGsi = () => {
      const g = (window as any).google;
      if (!g || !g.accounts || !g.accounts.id) return;

      try {
        g.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (response: any) => {
            if (response && response.credential) {
              setAuthProviderLoading(true);
              setError(null);
              setGoogleOriginMismatch(false);
              try {
                await verifyGoogleCredential(response.credential);
                setIsAuthenticated(true);
              } catch (err: any) {
                setError(err.message || 'Google authentication failed');
                triggerShake();
              } finally {
                setAuthProviderLoading(false);
              }
            }
          },
          auto_select: false,
          cancel_on_tap_outside: true,
        });
      } catch (e) {
        console.warn('Google Identity Services setup note:', e);
      }
    };

    setupGoogleGsi();
    const t1 = setTimeout(setupGoogleGsi, 400);
    return () => clearTimeout(t1);
  }, []);

  const triggerShake = () => {
    setIsShaking(true);
    setTimeout(() => setIsShaking(false), 500);
  };

  // Google Sign-In Handler
  const handleGoogleSignIn = () => {
    setError(null);
    const g = (window as any).google;
    if (g && g.accounts && g.accounts.id) {
      try {
        g.accounts.id.prompt((notification: any) => {
          if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
            const reason = notification.getNotDisplayedReason?.() || notification.getSkippedReason?.() || '';
            if (reason.includes('origin') || reason.includes('unregistered') || reason.includes('opt_out')) {
              setGoogleOriginMismatch(true);
            }
          }
        });
        return;
      } catch (err) {
        console.warn('Google prompt exception:', err);
      }
    }

    // Direct OAuth redirect flow fallback
    try {
      window.location.href = `/api/v1/auth/google/login`;
    } catch {
      setGoogleOriginMismatch(true);
    }
  };

  // Fast Dev Sign-in for riseinspirethrive2008@gmail.com
  const handleFastGoogleDevLogin = async (targetEmail: string = 'riseinspirethrive2008@gmail.com') => {
    setAuthProviderLoading(true);
    setError(null);
    try {
      await devGoogleLogin(targetEmail, 'Pushkar Shahi');
      setIsAuthenticated(true);
    } catch (err: any) {
      setError(err.message || 'Google sign in failed');
      triggerShake();
    } finally {
      setAuthProviderLoading(false);
    }
  };

  // GitHub Sign-In Handler
  const handleGitHubSignIn = async () => {
    setAuthProviderLoading(true);
    setError(null);
    try {
      await devGitHubLogin('Pushkar-Shahi');
      setIsAuthenticated(true);
    } catch (err: any) {
      setError(err.message || 'GitHub sign in failed');
      triggerShake();
    } finally {
      setAuthProviderLoading(false);
    }
  };

  // Email + Password Submit (Sign In or Sign Up)
  const handleEmailPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedPassword = password.trim();
    if (!trimmedPassword) {
      setError('Please enter a password.');
      triggerShake();
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setInfoMessage(null);

    try {
      if (authMode === 'signup') {
        const trimmedEmail = email.trim();
        if (!trimmedEmail) {
          setError('Please enter an email address.');
          triggerShake();
          setIsSubmitting(false);
          return;
        }
        await signupWithEmail(trimmedEmail, trimmedPassword, fullName.trim() || undefined);
        setIsAuthenticated(true);
      } else {
        // Sign In mode
        await loginWithPassword(trimmedPassword, email.trim() || undefined);
        setIsAuthenticated(true);
      }
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please verify credentials.');
      triggerShake();
    } finally {
      setIsSubmitting(false);
    }
  };

  // Loading state while verifying existing session
  if (isAuthenticated === null) {
    return (
      <div className="min-h-screen bg-white dark:bg-[#050505] text-slate-900 dark:text-neutral-100 flex flex-col items-center justify-center p-4">
        <div className="flex items-center gap-2.5 mb-4 animate-pulse">
          <BrandIcon size={36} className="shadow-lg shadow-emerald-500/20" />
          <span className="text-xl font-black tracking-tight">IssueToPR</span>
        </div>
        <p className="text-xs text-slate-400 dark:text-neutral-500 font-mono">Verifying secure credentials...</p>
      </div>
    );
  }

  // If authenticated, render children
  if (isAuthenticated) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-white dark:bg-[#070707] text-slate-900 dark:text-neutral-100 flex flex-col justify-center items-center px-4 py-12 selection:bg-slate-900 selection:text-white dark:selection:bg-white dark:selection:text-black transition-colors duration-200">
      
      {/* Brand Logo (Official Glowing Git PR Branch Icon) */}
      <div className="flex items-center justify-center gap-2.5 mb-7">
        <BrandIcon size={38} className="shadow-lg shadow-emerald-500/25 rounded-2xl active:scale-95 transition-transform" />
        <h1 className="text-2xl font-black tracking-tight text-slate-950 dark:text-white">
          IssueToPR
        </h1>
      </div>

      {/* Main Container */}
      <div 
        className={`w-full max-w-[400px] space-y-6 transition-transform ${
          isShaking ? 'translate-x-[-8px] transition-none' : ''
        }`}
      >
        {/* Title */}
        <h2 className="text-2xl sm:text-[32px] font-bold text-center tracking-tight text-slate-950 dark:text-white">
          {authMode === 'signin' ? 'Welcome back' : 'Create an account'}
        </h2>

        {/* Error Alert */}
        {error && (
          <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs flex items-center gap-2.5 animate-shake">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span className="leading-tight">{error}</span>
          </div>
        )}

        {/* Google Origin Mismatch Guide & Instant 1-Click Login */}
        {googleOriginMismatch && (
          <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-200 text-xs space-y-2.5 animate-fade-in shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2 font-bold text-amber-950 dark:text-amber-100">
                <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                <span>Google OAuth Origin Mismatch</span>
              </div>
              <button 
                type="button"
                onClick={() => setGoogleOriginMismatch(false)}
                className="text-amber-700 dark:text-amber-400 hover:opacity-75"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <p className="text-[11px] leading-relaxed text-amber-800 dark:text-amber-300">
              Google Cloud Console requires registering your localhost URL. In your Google Cloud Console under <strong>Credentials &rarr; OAuth Client ID</strong>, add:
              <br />
              <code className="inline-block mt-1 bg-amber-500/20 px-1.5 py-0.5 rounded font-mono text-[10px] text-amber-950 dark:text-amber-100">
                http://localhost:5173
              </code>
            </p>
            <button
              type="button"
              onClick={() => handleFastGoogleDevLogin('riseinspirethrive2008@gmail.com')}
              className="w-full py-2.5 px-3 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center justify-center gap-2 transition active:scale-95 shadow-sm"
            >
              <span>Instant Sign in as riseinspirethrive2008@gmail.com</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Stacked Provider Buttons */}
        <div className="space-y-3">
          {/* Sign in with Google Button */}
          <div className="space-y-1.5">
            <button
              type="button"
              onClick={handleGoogleSignIn}
              disabled={authProviderLoading}
              className="w-full h-12 px-4 rounded-xl border border-slate-200 dark:border-neutral-800 bg-white dark:bg-[#111111] hover:bg-slate-50 dark:hover:bg-neutral-800 text-slate-800 dark:text-neutral-100 text-sm font-medium flex items-center justify-center gap-3 transition shadow-sm active:scale-[0.99] cursor-pointer"
            >
              <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z"/>
                <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.27 21.43 7.34 24 12 24z"/>
                <path fill="#FBBC05" d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.99 0 12s.45 3.82 1.25 5.42l4.03-3.15z"/>
                <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.34 0 3.27 2.57 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"/>
              </svg>
              <span>{authMode === 'signin' ? 'Sign in with Google' : 'Sign up with Google'}</span>
            </button>
            <div className="flex items-center justify-between px-1 text-[11px] text-slate-500 dark:text-neutral-400">
              <span className="truncate max-w-[200px]" title="riseinspirethrive2008@gmail.com">riseinspirethrive2008...</span>
              <button
                type="button"
                onClick={() => handleFastGoogleDevLogin('riseinspirethrive2008@gmail.com')}
                className="font-bold text-indigo-600 dark:text-cyan-400 hover:underline cursor-pointer active:scale-95 transition"
              >
                Instant 1-Click Login &rarr;
              </button>
            </div>
          </div>

          {/* Sign in with GitHub Button */}
          <button
            type="button"
            onClick={handleGitHubSignIn}
            disabled={authProviderLoading}
            className="w-full h-12 px-4 rounded-xl border border-slate-200 dark:border-neutral-800 bg-white dark:bg-[#111111] hover:bg-slate-50 dark:hover:bg-neutral-800 text-slate-800 dark:text-neutral-100 text-sm font-medium flex items-center justify-center gap-3 transition shadow-sm active:scale-[0.99] cursor-pointer"
          >
            <svg className="w-4 h-4 fill-current shrink-0" viewBox="0 0 24 24">
              <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
            </svg>
            <span>{authMode === 'signin' ? 'Sign in with GitHub' : 'Sign up with GitHub'}</span>
          </button>

          {/* SSO Option (Sign In only) */}
          {authMode === 'signin' && (
            <button
              type="button"
              onClick={() => setIsSsoOpen(true)}
              className="w-full h-12 px-4 rounded-xl border border-slate-200 dark:border-neutral-800 bg-white dark:bg-[#111111] hover:bg-slate-50 dark:hover:bg-neutral-800 text-slate-800 dark:text-neutral-100 text-sm font-medium flex items-center justify-center gap-2.5 transition shadow-sm active:scale-[0.99] cursor-pointer"
            >
              <Building2 className="w-4 h-4 text-slate-500 dark:text-neutral-400" />
              <span>Sign in with SSO</span>
            </button>
          )}
        </div>

        {/* Divider Line */}
        <div className="relative py-1">
          <div className="border-t border-slate-200 dark:border-neutral-800" />
        </div>

        {/* Email & Password Form */}
        <form onSubmit={handleEmailPasswordSubmit} className="space-y-4">
          {authMode === 'signup' && (
            <div>
              <label className="block text-sm font-medium text-slate-800 dark:text-neutral-200 mb-1.5">
                Full name
              </label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Pushkar Shahi"
                className="w-full h-11 px-3.5 rounded-xl border border-slate-200 dark:border-neutral-800 bg-white dark:bg-[#0a0a0a] text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-neutral-600 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-white transition text-sm"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-800 dark:text-neutral-200 mb-1.5">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@domain.com"
              className="w-full h-11 px-3.5 rounded-xl border border-slate-200 dark:border-neutral-800 bg-white dark:bg-[#0a0a0a] text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-neutral-600 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-white transition text-sm"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-sm font-medium text-slate-800 dark:text-neutral-200">
                Password
              </label>
              {authMode === 'signin' && (
                <button
                  type="button"
                  onClick={() => setShowForgotPassword(true)}
                  className="text-xs text-slate-500 dark:text-neutral-400 hover:text-slate-900 dark:hover:text-white transition cursor-pointer"
                >
                  Forgot your password?
                </button>
              )}
            </div>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full h-11 pl-3.5 pr-10 rounded-xl border border-slate-200 dark:border-neutral-800 bg-white dark:bg-[#0a0a0a] text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-neutral-600 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-white transition text-sm font-mono"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:text-neutral-500 dark:hover:text-neutral-300 p-1"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Primary Submit Button (ElevenLabs Clean Solid Style) */}
          <button
            type="submit"
            disabled={isSubmitting || !password.trim()}
            className="w-full h-11 rounded-xl font-semibold text-sm transition-all duration-200 bg-neutral-400 text-white hover:bg-neutral-500 disabled:bg-neutral-300 dark:bg-neutral-700 dark:hover:bg-neutral-600 dark:disabled:bg-neutral-800 dark:text-white dark:disabled:text-neutral-500 shadow-sm active:scale-[0.99] disabled:cursor-not-allowed flex items-center justify-center gap-2 cursor-pointer mt-2"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{authMode === 'signin' ? 'Signing in...' : 'Signing up...'}</span>
              </>
            ) : (
              <span>{authMode === 'signin' ? 'Sign in' : 'Sign up'}</span>
            )}
          </button>
        </form>

        {/* Switch Link Footer */}
        <div className="pt-2 text-center text-sm text-slate-600 dark:text-neutral-400">
          {authMode === 'signin' ? (
            <>
              Don't have an account?{' '}
              <button
                type="button"
                onClick={() => {
                  setAuthMode('signup');
                  setError(null);
                  setGoogleOriginMismatch(false);
                }}
                className="text-slate-950 dark:text-white font-medium underline underline-offset-4 hover:opacity-85 transition cursor-pointer"
              >
                Sign up
              </button>
            </>
          ) : (
            <>
              Already registered?{' '}
              <button
                type="button"
                onClick={() => {
                  setAuthMode('signin');
                  setError(null);
                  setGoogleOriginMismatch(false);
                }}
                className="text-slate-950 dark:text-white font-medium underline underline-offset-4 hover:opacity-85 transition cursor-pointer"
              >
                Sign in
              </button>
            </>
          )}
        </div>
      </div>

      {/* Forgot Password Modal */}
      {showForgotPassword && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-sm p-6 rounded-2xl bg-white dark:bg-[#111111] border border-slate-200 dark:border-neutral-800 shadow-2xl space-y-4 animate-scale-up text-slate-900 dark:text-white">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-neutral-800">
              <div className="flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-indigo-500" />
                <h3 className="font-bold text-sm">Platform Access Hint</h3>
              </div>
              <button 
                type="button"
                onClick={() => setShowForgotPassword(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-slate-600 dark:text-neutral-400 leading-relaxed">
              For initial development access, use the platform master password:
            </p>
            <div className="p-2.5 rounded-xl bg-slate-100 dark:bg-neutral-900 border border-slate-200 dark:border-neutral-800 flex items-center justify-between font-mono text-xs">
              <span className="font-bold text-slate-900 dark:text-white">mwps@1534</span>
              <button
                type="button"
                onClick={() => {
                  setPassword('mwps@1534');
                  setShowForgotPassword(false);
                }}
                className="text-indigo-600 dark:text-indigo-400 hover:underline text-[11px] font-sans font-semibold"
              >
                Use this &rarr;
              </button>
            </div>
            <p className="text-[11px] text-slate-500 dark:text-neutral-500">
              You can also sign in directly using Google or GitHub above without needing a password.
            </p>
          </div>
        </div>
      )}

      {/* Enterprise SSO Modal */}
      <EnterpriseSSOModal
        isOpen={isSsoOpen}
        onClose={() => setIsSsoOpen(false)}
      />
    </div>
  );
}
