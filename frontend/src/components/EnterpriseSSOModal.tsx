import React, { useState, useEffect } from 'react';
import { Shield, Key, CheckCircle2, AlertTriangle, ExternalLink, X, RefreshCw, Lock } from 'lucide-react';
import { SSOConfig, SSOTestResult } from '../types';
import * as api from '../api';

interface EnterpriseSSOModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const EnterpriseSSOModal: React.FC<EnterpriseSSOModalProps> = ({ isOpen, onClose }) => {
  const [config, setConfig] = useState<SSOConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<SSOTestResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form state
  const [provider, setProvider] = useState<string>('okta');
  const [metadataUrl, setMetadataUrl] = useState<string>('');
  const [entityId, setEntityId] = useState<string>('');
  const [enforced, setEnforced] = useState<boolean>(false);

  useEffect(() => {
    if (!isOpen) return;

    const loadConfig = async () => {
      try {
        setLoading(true);
        const data = await api.fetchSSOConfig();
        setConfig(data);
        if (data.sso_provider) setProvider(data.sso_provider);
        if (data.sso_metadata_url) setMetadataUrl(data.sso_metadata_url);
        if (data.sso_entity_id) setEntityId(data.sso_entity_id);
        setEnforced(Boolean(data.sso_enforced));
      } catch (err: any) {
        console.error('Failed to load SSO config:', err);
      } finally {
        setLoading(false);
      }
    };

    loadConfig();
  }, [isOpen]);

  if (!isOpen) return null;

  const handleTestConnection = async () => {
    if (!metadataUrl.trim()) {
      setErrorMessage('Please enter a valid IdP Metadata URL before testing.');
      return;
    }
    try {
      setTesting(true);
      setErrorMessage(null);
      setTestResult(null);
      const res = await api.testSSOConnection({
        metadata_url: metadataUrl.trim(),
        provider
      });
      setTestResult(res);
    } catch (err: any) {
      setErrorMessage(err.message || 'SSO connection test failed.');
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!metadataUrl.trim()) {
      setErrorMessage('IdP Metadata URL is required.');
      return;
    }
    try {
      setSaving(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      const updated = await api.updateSSOConfig({
        sso_provider: provider,
        sso_metadata_url: metadataUrl.trim(),
        sso_entity_id: entityId.trim() || undefined,
        sso_enforced: enforced
      });
      setConfig(updated);
      setSuccessMessage('✓ Enterprise SSO configured successfully.');
      setTimeout(() => setSuccessMessage(null), 3500);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to save SSO configuration.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-xl rounded-2xl bg-[#0c101a] border border-white/15 p-6 shadow-2xl space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-purple-950/50 border border-purple-500/30 flex items-center justify-center text-purple-400">
              <Shield className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                Enterprise SAML 2.0 & OIDC SSO
              </h3>
              <p className="text-[11px] text-neutral-400">
                Centralize authentication and enforce identity governance via corporate IdP.
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="text-neutral-400 hover:text-white p-1 rounded-lg text-sm"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Status Messages */}
        {errorMessage && (
          <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{errorMessage}</span>
          </div>
        )}

        {successMessage && (
          <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
            <span>{successMessage}</span>
          </div>
        )}

        {loading ? (
          <div className="p-12 text-center text-neutral-500 flex flex-col items-center gap-2">
            <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
            <span className="text-xs">Loading enterprise security profile...</span>
          </div>
        ) : (
          <form onSubmit={handleSave} className="space-y-4">
            {/* Provider Selector */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-neutral-300">Identity Provider (IdP)</label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-[#05080f] border border-white/10 text-white text-xs focus:outline-none focus:border-white/30 transition cursor-pointer"
              >
                <option value="okta" className="bg-[#0c101a] text-white">Okta Workforce Identity</option>
                <option value="azure_ad" className="bg-[#0c101a] text-white">Microsoft Entra ID (Azure AD)</option>
                <option value="google" className="bg-[#0c101a] text-white">Google Workspace Enterprise SAML</option>
                <option value="onelogin" className="bg-[#0c101a] text-white">OneLogin</option>
                <option value="custom_saml" className="bg-[#0c101a] text-white">Custom SAML 2.0 / OIDC</option>
              </select>
            </div>

            {/* Metadata URL */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-neutral-300">
                IdP Metadata URL <span className="text-rose-400">*</span>
              </label>
              <input
                type="url"
                value={metadataUrl}
                onChange={(e) => setMetadataUrl(e.target.value)}
                placeholder="https://company.okta.com/app/exk123456/sso/saml/metadata"
                required
                className="w-full px-3.5 py-2.5 rounded-xl bg-[#05080f] border border-white/10 text-white placeholder-neutral-500 text-xs font-mono focus:outline-none focus:border-white/30 transition"
              />
              <p className="text-[11px] text-neutral-500 font-mono">
                Federation metadata XML or OpenID configuration URL provided by your identity team.
              </p>
            </div>

            {/* Entity ID */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-neutral-300">SP Entity ID / Audience URI (Optional)</label>
              <input
                type="text"
                value={entityId}
                onChange={(e) => setEntityId(e.target.value)}
                placeholder="https://issuetopr.dev/sso/saml/entity"
                className="w-full px-3.5 py-2.5 rounded-xl bg-[#05080f] border border-white/10 text-white placeholder-neutral-500 text-xs font-mono focus:outline-none focus:border-white/30 transition"
              />
            </div>

            {/* Enforce SSO Switch */}
            <div className="p-3 rounded-xl bg-[#05080f] border border-white/10 flex items-center justify-between">
              <div className="space-y-0.5">
                <span className="text-xs font-bold text-white flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5 text-amber-400" />
                  Enforce SSO for All Organization Members
                </span>
                <p className="text-[11px] text-neutral-400">
                  Disables local password logins. Users must authenticate through corporate IdP.
                </p>
              </div>
              <input
                type="checkbox"
                checked={enforced}
                onChange={(e) => setEnforced(e.target.checked)}
                className="w-4 h-4 rounded border-white/20 text-white focus:ring-0 cursor-pointer"
              />
            </div>

            {/* Test Connection Result Box */}
            {testResult && (
              <div className="p-3.5 rounded-xl bg-purple-950/30 border border-purple-500/30 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-purple-300 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-purple-400" />
                    {testResult.message}
                  </span>
                  <span className="text-[10px] font-mono uppercase bg-purple-900/60 px-2 py-0.5 rounded text-purple-200">
                    {testResult.status}
                  </span>
                </div>
                {testResult.endpoints_detected && (
                  <div className="space-y-1 font-mono text-[10px] text-neutral-300 pt-1 border-t border-purple-500/20">
                    <div>Login URL: {testResult.endpoints_detected.sso_login_url}</div>
                    <div>Fingerprint: {testResult.endpoints_detected.cert_fingerprint}</div>
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="pt-2 flex items-center justify-between gap-2 border-t border-white/10">
              <button
                type="button"
                onClick={handleTestConnection}
                disabled={testing || !metadataUrl.trim()}
                className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-neutral-900 hover:bg-neutral-800 text-neutral-200 border border-white/15 flex items-center gap-1.5 active:scale-95 transition disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
                <span>{testing ? 'Probing IdP...' : 'Test IdP Connection'}</span>
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 rounded-xl text-xs font-semibold bg-transparent text-neutral-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 rounded-xl text-xs font-semibold bg-white text-black hover:bg-neutral-200 active:scale-95 transition disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save Configuration'}
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

