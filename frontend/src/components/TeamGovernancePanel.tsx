import React, { useEffect, useState } from 'react';
import {
  Users, UserPlus, Trash2, Lock, RefreshCw, Key,
  ShieldCheck, CheckCircle2, AlertTriangle, Loader2, GitBranch, Sparkles
} from 'lucide-react';
import {
  Organization,
  OrganizationMember,
  PlatformSettings,
  PrivateRepositorySummary,
} from '../types';
import * as api from '../api';

interface TeamGovernancePanelProps {
  settings: PlatformSettings | null;
  onSettingsUpdated?: (updated: PlatformSettings) => void;
}

export const TeamGovernancePanel: React.FC<TeamGovernancePanelProps> = ({
  settings,
  onSettingsUpdated,
}) => {
  const [activeOrg, setActiveOrg] = useState<Organization | null>(null);
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [privateRepos, setPrivateRepos] = useState<PrivateRepositorySummary[]>([]);
  const [privateTierLocked, setPrivateTierLocked] = useState(false);

  const [loading, setLoading] = useState(true);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Member invite form
  const [inviteIdentifier, setInviteIdentifier] = useState('');
  const [inviteRole, setInviteRole] = useState<'member' | 'admin' | 'owner'>('member');
  const [inviting, setInviting] = useState(false);

  // Private repo sync form
  const [privateRepoInput, setPrivateRepoInput] = useState('');
  const [syncingPrivate, setSyncingPrivate] = useState(false);

  // Org shared BYOK keys & triage policy
  const [orgGeminiKey, setOrgGeminiKey] = useState('');
  const [orgOpenaiKey, setOrgOpenaiKey] = useState('');
  const [orgAnthropicKey, setOrgAnthropicKey] = useState('');
  const [orgCustomKey, setOrgCustomKey] = useState('');
  const [customEndpoint, setCustomEndpoint] = useState(settings?.custom_endpoint || '');
  const [enforceSharedKeys, setEnforceSharedKeys] = useState(Boolean(settings?.enforce_shared_keys));
  const [requireMaintainerApproval, setRequireMaintainerApproval] = useState(
    Boolean(settings?.triage_policy?.require_maintainer_approval)
  );
  const [minSuitabilityScore, setMinSuitabilityScore] = useState<number>(
    Number(settings?.triage_policy?.min_suitability_score ?? 40)
  );
  const [savingOrgPolicy, setSavingOrgPolicy] = useState(false);

  const loadGovernance = async () => {
    setLoading(true);
    try {
      const orgs = await api.fetchOrganizations();
      const current = orgs.find((o) => o.is_active) || orgs[0] || null;
      setActiveOrg(current);

      if (current) {
        const memList = await api.fetchOrganizationMembers(current.id).catch(() => []);
        setMembers(memList);

        try {
          const privs = await api.fetchOrgPrivateRepos(current.id);
          setPrivateRepos(privs);
          setPrivateTierLocked(false);
        } catch (err: any) {
          if (err.code === 'TIER_UPGRADE_REQUIRED') {
            setPrivateTierLocked(true);
          }
        }
      }
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Failed to load workspace governance.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGovernance();
  }, []);

  useEffect(() => {
    if (!settings) return;
    setEnforceSharedKeys(Boolean(settings.enforce_shared_keys));
    setCustomEndpoint(settings.custom_endpoint || '');
    setRequireMaintainerApproval(Boolean(settings.triage_policy?.require_maintainer_approval));
    setMinSuitabilityScore(Number(settings.triage_policy?.min_suitability_score ?? 40));
  }, [settings]);

  const canManage = activeOrg ? activeOrg.role === 'owner' || activeOrg.role === 'admin' : true;

  const handleInviteMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeOrg || !inviteIdentifier.trim()) return;
    setInviting(true);
    setStatusMsg(null);
    try {
      const added = await api.addOrganizationMember(activeOrg.id, inviteIdentifier.trim(), inviteRole);
      setMembers((prev) => [...prev, added]);
      setInviteIdentifier('');
      setStatusMsg({ type: 'success', text: `✓ Added @${added.username} as ${added.role}.` });
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Failed to invite member' });
    } finally {
      setInviting(false);
    }
  };

  const handleRoleChange = async (memberId: string, role: string) => {
    if (!activeOrg) return;
    setStatusMsg(null);
    try {
      const updated = await api.updateOrganizationMemberRole(activeOrg.id, memberId, role);
      setMembers((prev) => prev.map((m) => (m.id === memberId ? updated : m)));
      setStatusMsg({ type: 'success', text: `✓ Updated @${updated.username} role to ${updated.role}.` });
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Failed to update role' });
    }
  };

  const handleRemoveMember = async (member: OrganizationMember) => {
    if (!activeOrg) return;
    setStatusMsg(null);
    try {
      await api.removeOrganizationMember(activeOrg.id, member.id);
      setMembers((prev) => prev.filter((m) => m.id !== member.id));
      setStatusMsg({ type: 'success', text: `Removed @${member.username} from ${activeOrg.name}.` });
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Failed to remove member' });
    }
  };

  const handleSyncPrivateRepos = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeOrg) return;
    setSyncingPrivate(true);
    setStatusMsg(null);
    try {
      const raw = privateRepoInput.trim().replace(/^https?:\/\/github\.com\//i, '').replace(/\/+$/, '');
      const payload = raw
        ? raw.includes('/')
          ? { repo_full_name: raw }
          : { org_name: raw }
        : {};
      const res = await api.syncOrgPrivateRepos(activeOrg.id, payload);
      const privs = await api.fetchOrgPrivateRepos(activeOrg.id);
      setPrivateRepos(privs);
      setPrivateRepoInput('');
      setStatusMsg({
        type: 'success',
        text: `✓ Synced ${res.synced_repos} private repositories and ${res.synced_issues} issues into ${activeOrg.name}.`,
      });
    } catch (err: any) {
      if (err.code === 'TIER_UPGRADE_REQUIRED') {
        setPrivateTierLocked(true);
      }
      setStatusMsg({ type: 'error', text: err.message || 'Private repo sync failed' });
    } finally {
      setSyncingPrivate(false);
    }
  };

  const handleSaveOrgSharedPolicy = async () => {
    setSavingOrgPolicy(true);
    setStatusMsg(null);
    try {
      const updated = await api.updateSettings({
        scope: 'organization',
        enforce_shared_keys: enforceSharedKeys,
        org_gemini_api_key: orgGeminiKey.trim() || undefined,
        org_openai_api_key: orgOpenaiKey.trim() || undefined,
        org_anthropic_api_key: orgAnthropicKey.trim() || undefined,
        org_custom_api_key: orgCustomKey.trim() || undefined,
        custom_endpoint: customEndpoint.trim() || undefined,
        triage_policy: {
          require_maintainer_approval: requireMaintainerApproval,
          min_suitability_score: minSuitabilityScore,
        },
      });
      setOrgGeminiKey('');
      setOrgOpenaiKey('');
      setOrgAnthropicKey('');
      setOrgCustomKey('');
      if (onSettingsUpdated) onSettingsUpdated(updated);
      setStatusMsg({ type: 'success', text: '✓ Organization shared BYOK keys and triage policy saved.' });
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Failed to save organization policy' });
    } finally {
      setSavingOrgPolicy(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 flex items-center justify-center gap-2 text-xs text-slate-500 dark:text-neutral-400">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Loading team seats, private repos, and RBAC governance...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {statusMsg && (
        <div
          className={`p-3.5 rounded-xl border text-xs flex items-center justify-between ${
            statusMsg.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-950/30 dark:border-emerald-500/30 dark:text-emerald-300'
              : 'bg-rose-50 border-rose-200 text-rose-800 dark:bg-rose-950/30 dark:border-rose-500/30 dark:text-rose-300'
          }`}
        >
          <div className="flex items-center gap-2">
            {statusMsg.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 shrink-0" />
            )}
            <span>{statusMsg.text}</span>
          </div>
          <button onClick={() => setStatusMsg(null)} className="underline text-[11px] ml-4">
            Dismiss
          </button>
        </div>
      )}

      {/* 1. Multi-User Seats & RBAC Governance */}
      <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100 dark:border-white/10">
          <div className="flex items-center gap-2.5">
            <Users className="w-4 h-4 text-blue-600 dark:text-cyan-400" />
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Multi-User Seats & RBAC Governance
              </h3>
              <p className="text-[11px] text-slate-500 dark:text-neutral-400">
                Active Workspace: <strong>{activeOrg?.name || 'Personal Workspace'}</strong> • Your Role:{' '}
                <span className="uppercase font-mono">{activeOrg?.role || 'owner'}</span>
              </p>
            </div>
          </div>
          <span className="text-[11px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-500/30">
            {members.length} {members.length === 1 ? 'Seat' : 'Seats'}
          </span>
        </div>

        {canManage && (
          <form onSubmit={handleInviteMember} className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              value={inviteIdentifier}
              onChange={(e) => setInviteIdentifier(e.target.value)}
              placeholder="GitHub username or teammate email..."
              className="flex-1 bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
            />
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as any)}
              className="bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-3 py-2.5 text-xs text-slate-800 dark:text-white focus:outline-none"
            >
              <option value="member">Member (Run tasks & PRs)</option>
              <option value="admin">Admin (Manage org & keys)</option>
              <option value="owner">Owner (Full governance)</option>
            </select>
            <button
              type="submit"
              disabled={inviting || !inviteIdentifier.trim()}
              className="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-sm transition active:scale-95 disabled:opacity-50"
            >
              {inviting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UserPlus className="w-3.5 h-3.5" />}
              <span>Invite Seat</span>
            </button>
          </form>
        )}

        <div className="divide-y divide-slate-100 dark:divide-white/10">
          {members.map((m) => (
            <div key={m.id} className="py-3 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-8 h-8 rounded-full bg-slate-200 dark:bg-white/10 flex items-center justify-center text-xs font-bold text-slate-800 dark:text-white uppercase shrink-0">
                  {m.username.slice(0, 1)}
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-bold text-slate-900 dark:text-white truncate">@{m.username}</div>
                  <div className="text-[11px] text-slate-500 dark:text-neutral-400 truncate">
                    {m.email || m.name || 'Contributor'}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {canManage ? (
                  <>
                    <select
                      value={m.role}
                      onChange={(e) => handleRoleChange(m.id, e.target.value)}
                      className="bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-lg px-2.5 py-1 text-[11px] font-semibold text-slate-800 dark:text-white"
                    >
                      <option value="owner">owner</option>
                      <option value="admin">admin</option>
                      <option value="member">member</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => handleRemoveMember(m)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition"
                      title="Remove seat"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </>
                ) : (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase bg-slate-100 dark:bg-white/10 text-slate-700 dark:text-neutral-300">
                    {m.role}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 2. Private GitHub Organizations & Repositories */}
      <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-100 dark:border-white/10">
          <div className="flex items-center gap-2.5">
            <Lock className="w-4 h-4 text-purple-600 dark:text-purple-400" />
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Private GitHub Organizations & Repositories
              </h3>
              <p className="text-[11px] text-slate-500 dark:text-neutral-400">
                Issues synced here remain strictly isolated to <strong>{activeOrg?.name || 'this workspace'}</strong>.
              </p>
            </div>
          </div>
          <span className="text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-500/30">
            TEAM TIER
          </span>
        </div>

        {privateTierLocked ? (
          <div className="p-4 rounded-xl bg-amber-50/80 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-500/30 text-xs text-amber-800 dark:text-amber-300">
            Upgrade to <strong>Engineering Team (₹300/mo)</strong> in Billing to connect and sync private GitHub repositories & organizations.
          </div>
        ) : (
          <>
            <form onSubmit={handleSyncPrivateRepos} className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                value={privateRepoInput}
                onChange={(e) => setPrivateRepoInput(e.target.value)}
                placeholder="owner/private-repo, GitHub org slug, or leave blank to sync all..."
                className="flex-1 bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/40"
              />
              <button
                type="submit"
                disabled={syncingPrivate || !canManage}
                className="px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-sm transition active:scale-95 disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${syncingPrivate ? 'animate-spin' : ''}`} />
                <span>{syncingPrivate ? 'Syncing Private...' : 'Sync Private Repos'}</span>
              </button>
            </form>

            {privateRepos.length === 0 ? (
              <p className="text-xs text-slate-500 dark:text-neutral-400">
                No private repositories connected yet. Ensure your GitHub PAT includes the <code className="font-mono">repo</code> scope, then click Sync Private Repos.
              </p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {privateRepos.map((repo) => (
                  <div
                    key={repo.id}
                    className="p-3 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 flex items-center justify-between gap-2"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <GitBranch className="w-3.5 h-3.5 text-purple-500 shrink-0" />
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-slate-900 dark:text-white truncate">{repo.full_name}</div>
                        <div className="text-[10px] text-slate-500 dark:text-neutral-400">
                          {repo.primary_language || 'Repo'} • {repo.open_issues_count} open issues
                        </div>
                      </div>
                    </div>
                    <span className="text-[9px] font-mono px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300 font-bold shrink-0">
                      PRIVATE
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* 3. Shared Team BYOK AI Keys & Triage Policy */}
      <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-white/10">
          <div className="flex items-center gap-2.5">
            <Key className="w-4 h-4 text-emerald-500" />
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Shared Team BYOK AI Keys & Triage Policy
              </h3>
              <p className="text-[11px] text-slate-500 dark:text-neutral-400">
                Centralize encrypted organization API keys and enforce shared team triage policies.
              </p>
            </div>
          </div>
          <span className="text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30">
            TEAM RBAC
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div>
            <label className="block font-semibold text-slate-700 dark:text-neutral-300 mb-1">
              Org Shared Gemini Key {settings?.has_org_gemini_key ? '✓ Configured' : ''}
            </label>
            <input
              type="password"
              value={orgGeminiKey}
              onChange={(e) => setOrgGeminiKey(e.target.value)}
              disabled={!canManage}
              placeholder={settings?.org_gemini_api_key || 'AIzaSy... (organization shared key)'}
              className="w-full bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white disabled:opacity-60"
            />
          </div>
          <div>
            <label className="block font-semibold text-slate-700 dark:text-neutral-300 mb-1">
              Org Shared OpenAI Key {settings?.has_org_openai_key ? '✓ Configured' : ''}
            </label>
            <input
              type="password"
              value={orgOpenaiKey}
              onChange={(e) => setOrgOpenaiKey(e.target.value)}
              disabled={!canManage}
              placeholder={settings?.org_openai_api_key || 'sk-... (organization shared key)'}
              className="w-full bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white disabled:opacity-60"
            />
          </div>
          <div>
            <label className="block font-semibold text-slate-700 dark:text-neutral-300 mb-1">
              Org Shared Anthropic Key {settings?.has_org_anthropic_key ? '✓ Configured' : ''}
            </label>
            <input
              type="password"
              value={orgAnthropicKey}
              onChange={(e) => setOrgAnthropicKey(e.target.value)}
              disabled={!canManage}
              placeholder={settings?.org_anthropic_api_key || 'sk-ant-... (organization shared key)'}
              className="w-full bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white disabled:opacity-60"
            />
          </div>
          <div>
            <label className="block font-semibold text-slate-700 dark:text-neutral-300 mb-1">
              Org Custom / Local Endpoint URL
            </label>
            <input
              type="text"
              value={customEndpoint}
              onChange={(e) => setCustomEndpoint(e.target.value)}
              disabled={!canManage}
              placeholder="http://localhost:11434/v1"
              className="w-full bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs font-mono text-slate-900 dark:text-white disabled:opacity-60"
            />
          </div>
        </div>

        <div className="space-y-2.5 pt-2">
          <label className="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 cursor-pointer">
            <div>
              <div className="text-xs font-semibold text-slate-900 dark:text-white">
                Enforce Shared Organization BYOK Keys
              </div>
              <div className="text-[11px] text-slate-500 dark:text-neutral-400">
                When enabled, organization shared keys override members' personal keys during issue analysis.
              </div>
            </div>
            <input
              type="checkbox"
              checked={enforceSharedKeys}
              onChange={(e) => setEnforceSharedKeys(e.target.checked)}
              disabled={!canManage}
              className="w-4 h-4 accent-blue-600"
            />
          </label>

          <label className="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 cursor-pointer">
            <div>
              <div className="text-xs font-semibold text-slate-900 dark:text-white">
                Triage Policy: Require Maintainer Pre-Approval Comment
              </div>
              <div className="text-[11px] text-slate-500 dark:text-neutral-400">
                Routes all selected team tasks through maintainer assignment confirmation before coding begins.
              </div>
            </div>
            <input
              type="checkbox"
              checked={requireMaintainerApproval}
              onChange={(e) => setRequireMaintainerApproval(e.target.checked)}
              disabled={!canManage}
              className="w-4 h-4 accent-blue-600"
            />
          </label>

          <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10">
            <div>
              <div className="text-xs font-semibold text-slate-900 dark:text-white">
                Minimum Issue Suitability Threshold ({minSuitabilityScore}/100)
              </div>
              <div className="text-[11px] text-slate-500 dark:text-neutral-400">
                Team policy target score highlighted across automated triage briefs.
              </div>
            </div>
            <input
              type="range"
              min={10}
              max={90}
              step={5}
              value={minSuitabilityScore}
              onChange={(e) => setMinSuitabilityScore(Number(e.target.value))}
              disabled={!canManage}
              className="w-28 accent-blue-600"
            />
          </div>
        </div>

        {canManage && (
          <div className="flex justify-end pt-1">
            <button
              type="button"
              onClick={handleSaveOrgSharedPolicy}
              disabled={savingOrgPolicy}
              className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-2 shadow-sm transition active:scale-95 disabled:opacity-50"
            >
              {savingOrgPolicy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
              <span>{savingOrgPolicy ? 'Saving Policy...' : 'Save Shared Keys & Team Policy'}</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

