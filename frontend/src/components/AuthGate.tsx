import React, { useState, useEffect } from 'react';
import { Lock, Fingerprint, KeyRound, ShieldAlert, Sparkles, ArrowRight, Eye, EyeOff, CheckCircle2, ShieldCheck, AlertCircle, Clock } from 'lucide-react';
import { 
  loginWithPassword, 
  verifyAuth, 
  setAuthToken,
  setOnUnauthorized, 
  isBiometricsSupported, 
  loginWithBiometrics, 
  registerDeviceBiometrics, 
  getStoredBiometricCredentialId,
  getBiometricStatus,
  isSecureContextAvailable,
  getWebsiteInternalSchedule
} from '../api';

interface AuthGateProps {
  children: React.ReactNode;
}

export function AuthGate({ children }: AuthGateProps) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isShaking, setIsShaking] = useState(false);
  const [biometricsAvailable, setBiometricsAvailable] = useState(false);
  const [isBiometricScanning, setIsBiometricScanning] = useState(false);
  const [hasEnrolledBiometrics, setHasEnrolledBiometrics] = useState(false);
  const [rememberBiometrics, setRememberBiometrics] = useState(true);
  const [isSecure, setIsSecure] = useState(true);

  // Live 2-Hour Website Internal Timer State (runs independently before & across login)
  const [internalSchedule, setInternalSchedule] = useState(() => getWebsiteInternalSchedule());

  useEffect(() => {
    const tick = () => {
      setInternalSchedule(getWebsiteInternalSchedule());
    };
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, []);

  // Check auth & biometric availability on mount
  useEffect(() => {
    let mounted = true;
    const secure = isSecureContextAvailable();
    setIsSecure(secure);

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

    // Check biometric hardware support
    isBiometricsSupported().then((supported) => {
      if (mounted) {
        setBiometricsAvailable(supported);
        const storedId = getStoredBiometricCredentialId();
        if (storedId) {
          setHasEnrolledBiometrics(true);
        } else {
          getBiometricStatus().then(status => {
            if (mounted && status.has_registered_credentials) {
              setHasEnrolledBiometrics(true);
            }
          });
        }
      }
    });

    setOnUnauthorized(() => {
      setIsAuthenticated(false);
      setError('Session expired. Please unlock with fingerprint or password.');
    });

    return () => {
      mounted = false;
    };
  }, []);

  // Quick unlock using device fingerprint / Touch ID
  const handleBiometricUnlock = async () => {
    setError(null);
    setInfoMessage(null);

    if (!isSecure) {
      setError('Biometrics requires a secure HTTPS origin or http://localhost. Please use password or open via the hosted HTTPS link.');
      triggerShake();
      return;
    }

    const storedId = getStoredBiometricCredentialId();
    if (!storedId) {
      setInfoMessage('To activate Touch ID / device fingerprint, enter your password once below with "Sync fingerprint" checked.');
      return;
    }

    setIsBiometricScanning(true);

    try {
      await loginWithBiometrics();
      setIsAuthenticated(true);
    } catch (err: any) {
      console.warn('Biometric unlock attempt:', err);
      const msg = err.message || '';
      if (msg.includes('cancelled') || msg.includes('canceled') || msg.includes('AbortError')) {
        setInfoMessage('Fingerprint verification was cancelled. Touch sensor or enter password.');
      } else if (msg === 'NO_DEVICE_CREDENTIAL' || msg.includes('No credentials') || msg.includes('NotAllowedError')) {
        setInfoMessage('To link your device fingerprint, enter your password once below with "Sync fingerprint" checked.');
      } else {
        setError(msg || 'Fingerprint verification failed. Try again or enter password.');
        triggerShake();
      }
    } finally {
      setIsBiometricScanning(false);
    }
  };

  const handlePasswordUnlock = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) {
      setError('Please enter the access password.');
      triggerShake();
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setInfoMessage(null);

    try {
      const trimmed = password.trim();
      await loginWithPassword(trimmed);

      // If user enabled "Remember fingerprint" and hardware is available, register biometric credential
      if (biometricsAvailable && rememberBiometrics) {
        try {
          await registerDeviceBiometrics(trimmed);
          setHasEnrolledBiometrics(true);
        } catch (bioErr: any) {
          console.warn('Optional biometric enrollment note:', bioErr);
        }
      }

      setIsAuthenticated(true);
      setPassword('');
    } catch (err: any) {
      setError(err.message || 'Incorrect password. Access denied.');
      triggerShake();
    } finally {
      setIsSubmitting(false);
    }
  };

  const triggerShake = () => {
    setIsShaking(true);
    setTimeout(() => setIsShaking(false), 500);
  };

  // Initial loading state while verifying existing token
  if (isAuthenticated === null) {
    return (
      <div className="min-h-screen bg-[#000000] flex flex-col items-center justify-center p-4">
        <div className="w-12 h-12 rounded-2xl bg-neutral-900 border border-white/20 p-0.5 animate-pulse">
          <div className="w-full h-full bg-[#050505] rounded-2xl flex items-center justify-center">
            <Lock className="w-5 h-5 text-white animate-spin" />
          </div>
        </div>
        <p className="mt-4 text-xs font-mono text-neutral-400">Verifying security credentials...</p>
      </div>
    );
  }

  // If authenticated, render app
  if (isAuthenticated) {
    return <>{children}</>;
  }

  // Pure AMOLED Lock Screen view
  return (
    <div className="min-h-screen bg-[#000000] flex flex-col justify-between p-4 sm:p-6 text-neutral-100 select-none">
      {/* Top Brand Header */}
      <div className="flex items-center justify-between max-w-md w-full mx-auto pt-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-white text-black flex items-center justify-center shadow-lg shadow-white/10">
            <Sparkles className="w-4 h-4 text-black" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-white">
              Issue-to-PR
            </h1>
            <p className="text-[10px] text-neutral-400 font-mono">Autonomous GSoC Platform</p>
          </div>
        </div>
        <span className="text-[10px] px-2.5 py-1 rounded-full bg-neutral-900 border border-white/20 text-neutral-300 font-mono flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
          AMOLED SECURE
        </span>
      </div>

      {/* 2-Hour Autonomous Online Scanner Live Banner (Website Internal Timer) */}
      <div className="max-w-md w-full mx-auto mt-4 p-3.5 rounded-2xl bg-[#090909] border border-white/15 shadow-xl flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="relative flex items-center justify-center w-8 h-8 rounded-xl bg-white text-black shrink-0 shadow-md">
            <Clock className="w-4 h-4 text-black animate-pulse" />
            <span className="absolute -top-1 -right-1 w-2 h-2 bg-white rounded-full animate-ping" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-white font-bold text-xs">Autonomous 2H Scanner</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-neutral-900 text-neutral-300 border border-white/20 font-mono">
                Website Engine Active
              </span>
            </div>
            <p className="text-[10px] text-neutral-400 truncate">
              Continuous scan &bull; NumFOCUS, PSF, DeepChem, Kornia
            </p>
          </div>
        </div>
        <div className="flex flex-col items-end shrink-0">
          <span className="text-[9px] uppercase font-semibold text-neutral-400 font-mono">Next Scan In</span>
          <span className="text-xs font-mono font-extrabold text-white px-2 py-0.5 rounded-lg bg-neutral-900 border border-white/25 shadow-inner">
            {internalSchedule.formatted.digital}
          </span>
        </div>
      </div>

      {/* Main Lock Modal */}
      <div className="max-w-md w-full mx-auto my-auto py-6">
        <div 
          className={`relative bg-[#080808] border border-white/15 rounded-2xl p-6 sm:p-8 shadow-2xl shadow-black transition-transform ${
            isShaking ? 'translate-x-[-8px] transition-none' : ''
          }`}
        >
          {/* Subtle Monochrome Glow Backdrop */}
          <div className="absolute -top-16 -right-16 w-36 h-36 bg-white/[0.03] rounded-full blur-3xl pointer-events-none" />
          <div className="absolute -bottom-16 -left-16 w-36 h-36 bg-white/[0.03] rounded-full blur-3xl pointer-events-none" />

          {/* Insecure Origin Notice (if testing on phone via plain HTTP) */}
          {!isSecure && (
            <div className="mb-5 p-3 rounded-xl bg-[#141414] border border-white/20 text-[11px] text-neutral-300 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-white mt-0.5" />
              <div>
                <span className="font-semibold text-white">Notice for Mobile/LAN:</span> Browsers require HTTPS or localhost for fingerprint access. Use the hosted GitHub link for native mobile Touch ID / Fingerprint, or enter password below.
              </div>
            </div>
          )}

          {/* Biometric Sensor Icon Button */}
          <div className="flex flex-col items-center justify-center mb-6">
            <button
              type="button"
              onClick={handleBiometricUnlock}
              disabled={isBiometricScanning}
              className={`relative group p-4 rounded-3xl border transition-all duration-300 active:scale-95 ${
                isBiometricScanning
                  ? 'border-white bg-white/10 shadow-[0_0_35px_rgba(255,255,255,0.25)]'
                  : 'border-white/20 bg-neutral-900/80 hover:border-white/50 hover:bg-neutral-800'
              }`}
              title="Unlock using Device Fingerprint / Touch ID"
            >
              {/* Animated Scanner Beam */}
              {isBiometricScanning && (
                <div className="absolute inset-x-2 top-0 h-1 bg-white rounded-full blur-[1px] animate-scanner" />
              )}
              
              <div className="relative">
                <Fingerprint className={`w-12 h-12 transition-colors ${
                  isBiometricScanning ? 'text-white animate-pulse' : 'text-neutral-200 group-hover:text-white'
                }`} />
                <div className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full bg-black border border-white/30 flex items-center justify-center">
                  <Lock className="w-2.5 h-2.5 text-white" />
                </div>
              </div>
            </button>

            {biometricsAvailable && (
              <button
                type="button"
                onClick={handleBiometricUnlock}
                disabled={isBiometricScanning}
                className="mt-3 text-xs font-medium text-white hover:text-neutral-300 transition flex items-center gap-1.5 active:scale-95"
              >
                <span>{isBiometricScanning ? 'Scanning Fingerprint...' : 'Unlock with Fingerprint / Touch ID'}</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <div className="text-center mb-5">
            <h2 className="text-base font-bold text-white tracking-tight">
              Platform Locked
            </h2>
            <p className="text-xs text-neutral-400 mt-1">
              Use your device fingerprint sensor or enter your access password.
            </p>
          </div>

          {/* Informational Message */}
          {infoMessage && (
            <div className="mb-4 flex items-center gap-2 p-3 rounded-xl bg-neutral-900 border border-white/20 text-neutral-200 text-xs">
              <ShieldCheck className="w-4 h-4 shrink-0 text-white" />
              <span>{infoMessage}</span>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="mb-4 flex items-center gap-2 p-3 rounded-xl bg-neutral-900 border border-rose-500/50 text-rose-300 text-xs animate-fade-in-up">
              <ShieldAlert className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          {/* GitHub OAuth 2.0 Sign In Button */}
          <div className="mb-5">
            <button
              type="button"
              onClick={() => {
                window.location.href = '/api/v1/auth/github/login';
              }}
              className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-xl bg-[#1f2328] hover:bg-[#2d333b] text-white font-semibold text-sm border border-white/20 shadow-lg hover:border-white/40 transition active:scale-[0.98]"
            >
              <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
              </svg>
              <span>Sign in with GitHub</span>
            </button>
            <div className="relative my-4">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-white/10" />
              </div>
              <div className="relative flex justify-center text-[10px] uppercase">
                <span className="bg-[#080808] px-2 text-neutral-500 font-mono">Or use password / biometrics</span>
              </div>
            </div>
          </div>

          {/* Password Form */}
          <form onSubmit={handlePasswordUnlock} className="space-y-4">
            <div className="space-y-1.5">
              <label className="block text-[11px] font-medium text-neutral-300">
                Access Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password..."
                  autoFocus={!biometricsAvailable}
                  autoComplete="current-password"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#030303] border border-white/20 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-white focus:ring-1 focus:ring-white transition pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-white transition p-0.5"
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>

            {/* Remember device biometrics checkbox */}
            {biometricsAvailable && (
              <label className="flex items-center gap-2 text-xs text-neutral-400 cursor-pointer pt-1">
                <input
                  type="checkbox"
                  checked={rememberBiometrics}
                  onChange={(e) => setRememberBiometrics(e.target.checked)}
                  className="w-4 h-4 rounded bg-[#030303] border-white/30 text-white focus:ring-white focus:ring-offset-black accent-white cursor-pointer"
                />
                <span>Sync fingerprint with this device for 1-tap unlock</span>
              </label>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-white hover:bg-neutral-200 text-black font-semibold text-sm shadow-md transition disabled:opacity-50 active:scale-[0.98]"
            >
              {isSubmitting ? (
                <>
                  <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
                  <span>Unlocking...</span>
                </>
              ) : (
                <>
                  <span>Unlock with Password</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="mt-6 pt-4 border-t border-white/10 flex items-center justify-between text-[11px] text-neutral-500 font-mono">
            <span>WebAuthn Biometrics</span>
            <span>Encrypted Session</span>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="max-w-md w-full mx-auto text-center pb-4 text-[11px] text-neutral-500">
        AMOLED Engine &bull; Optimized for Laptop & Mobile
      </div>
    </div>
  );
}

export default AuthGate;
