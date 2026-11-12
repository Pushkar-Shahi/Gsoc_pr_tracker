import React, { useState, useEffect } from 'react';
import { 
  Key, Terminal, Check,
  AlertTriangle, Save, Plus, X, ShieldAlert, RefreshCw,
  Cpu, Sparkles, LogOut, CheckCircle2, User, Users, Webhook,
  Copy, Trash2, Sliders, Zap
} from 'lucide-react';
import { PlatformSettings, WebhookSubscription } from '../types';
import {
  logout, getCustomGitHubToken,
  fetchWebhookSubscriptions, createWebhookSubscription, deleteWebhookSubscription,
  triggerPrioritySync, updateRankingMatrix, rescoreIssues
} from '../api';
import { TeamGovernancePanel } from './TeamGovernancePanel';

export type SettingsSection = 'github' | 'ai' | 'automation' | 'skills' | 'team' | 'workspace' | 'account';

interface SettingsViewProps {
  settings: PlatformSettings | null;
  initialSection?: SettingsSection;
  onSaveSettings: (updated: Partial<PlatformSettings> & Record<string, any>) => Promise<void>;
  onSettingsUpdated?: (updated: PlatformSettings) => void;
}

const DEFAULT_TAG_KEYS = ['good first issue', 'help wanted', 'bug', 'enhancement', 'documentation'];

export const SettingsView: React.FC<SettingsViewProps> = ({
  settings,
  initialSection = 'github',
  onSaveSettings,
  onSettingsUpdated,
}) => {
  const [activeSection, setActiveSection] = useState<SettingsSection>(initialSection);

  useEffect(() => {
    if (initialSection) {
      setActiveSection(initialSection);
    }
  }, [initialSection]);

  // Form State with LocalStorage fallbacks
  const [token, setToken] = useState('');
  const [username, setUsername] = useState(() => 
    settings?.github_username || localStorage.getItem('issuetopr_gh_user') || 'Pushkar-Shahi'
  );
  const [autoPublish, setAutoPublish] = useState(() => 
    settings?.auto_publish_pr ?? false
  );
  const [workspaceRoot, setWorkspaceRoot] = useState(() => 
    settings?.workspace_root || '~/workspace/issue-to-pr'
  );
  const [skills, setSkills] = useState<string[]>(() => 
    settings?.skills_profile || ['python', 'pytorch', 'react', 'numpy', 'scipy', 'deepchem']
  );
  const [newSkill, setNewSkill] = useState('');

  // AI Provider Keys State
  const [geminiKey, setGeminiKey] = useState(() => localStorage.getItem('issuetopr_gemini_key') || '');
  const [claudeKey, setClaudeKey] = useState(() => localStorage.getItem('issuetopr_claude_key') || '');
  const [openaiKey, setOpenaiKey] = useState(() => localStorage.getItem('issuetopr_openai_key') || '');
  const [customKey, setCustomKey] = useState('');
  const [customEndpoint, setCustomEndpoint] = useState(settings?.custom_endpoint || '');
  const [preferredModel, setPreferredModel] = useState(() => 
    localStorage.getItem('issuetopr_preferred_ai') || settings?.preferred_ai_provider || 'gemini'
  );

  // Custom Weighting Matrix State (Pro)
  const [skillWeights, setSkillWeights] = useState<Record<string, number>>(
    () => settings?.skill_weights || {}
  );
  const [tagWeights, setTagWeights] = useState<Record<string, number>>(
    () => settings?.tag_weights || {}
  );
  const [matrixSaving, setMatrixSaving] = useState(false);

  // Real-time Webhooks & Priority Discovery State (Pro)
  const [webhooks, setWebhooks] = useState<WebhookSubscription[]>([]);
  const [webhookTierLocked, setWebhookTierLocked] = useState(false);
  const [newWebhookRepo, setNewWebhookRepo] = useState('');
  const [creatingWebhook, setCreatingWebhook] = useState(false);
  const [copiedSecretId, setCopiedSecretId] = useState<string | null>(null);
  const [prioritySyncing, setPrioritySyncing] = useState(false);

  // Status and Feedback
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [isTestingGitHub, setIsTestingGitHub] = useState(false);
  const [githubTestResult, setGithubTestResult] = useState<{
    success: boolean;
    login?: string;
    rateLimitRemaining?: number;
    message?: string;
  } | null>(null);

  // Synchronize state when settings prop updates
  useEffect(() => {
    if (settings) {
      if (settings.github_username) setUsername(settings.github_username);
      if (settings.auto_publish_pr !== undefined) setAutoPublish(settings.auto_publish_pr);
      if (settings.workspace_root) setWorkspaceRoot(settings.workspace_root);
      if (settings.skills_profile && Array.isArray(settings.skills_profile)) {
        setSkills(settings.skills_profile);
      }
      if (settings.custom_endpoint !== undefined) {
        setCustomEndpoint(settings.custom_endpoint || '');
      }
      if (settings.preferred_ai_provider) {
        setPreferredModel(settings.preferred_ai_provider);
      }
      if (settings.skill_weights) {
        setSkillWeights(settings.skill_weights);
      }
      if (settings.tag_weights) {
        setTagWeights(settings.tag_weights);
      }
    }
  }, [settings]);

  useEffect(() => {
    if (activeSection !== 'automation') return;
    fetchWebhookSubscriptions()
      .then((list) => {
        setWebhooks(list);
        setWebhookTierLocked(false);
      })
      .catch((err: any) => {
        if (err.code === 'TIER_UPGRADE_REQUIRED') {
          setWebhookTierLocked(true);
        }
      });
  }, [activeSection]);

  const handleSaveMatrixAndRescore = async () => {
    setMatrixSaving(true);
    setSaveMessage(null);
    try {
      await updateRankingMatrix(skillWeights, tagWeights);
      const res = await rescoreIssues();
      setSaveMessage(`✓ Saved custom weighting matrix and re-ranked ${res.rescored_count} open GSoC issues.`);
    } catch (err: any) {
      setSaveMessage(`Matrix notice: ${err.message}`);
    } finally {
      setMatrixSaving(false);
    }
  };

  const handleCreateWebhook = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWebhookRepo.trim()) return;
    setCreatingWebhook(true);
    setSaveMessage(null);
    try {
      const created = await createWebhookSubscription(newWebhookRepo.trim());
      setWebhooks((prev) => [created, ...prev]);
      setNewWebhookRepo('');
      setSaveMessage(`✓ Registered real-time webhook for ${created.repo_full_name}.`);
    } catch (err: any) {
      setSaveMessage(`Webhook notice: ${err.message}`);
    } finally {
      setCreatingWebhook(false);
    }
  };

  const handleDeleteWebhook = async (id: string) => {
    try {
      await deleteWebhookSubscription(id);
      setWebhooks((prev) => prev.filter((w) => w.id !== id));
    } catch (err: any) {
      setSaveMessage(`Webhook delete error: ${err.message}`);
    }
  };

  const handlePriorityDiscovery = async () => {
    setPrioritySyncing(true);
    setSaveMessage(null);
    try {
      const res = await triggerPrioritySync(undefined, true);
      setSaveMessage(`✓ Priority discovery sync finished (${res.discovered ?? 0} issues synced).`);
    } catch (err: any) {
      setSaveMessage(`Priority sync notice: ${err.message}`);
    } finally {
      setPrioritySyncing(false);
    }
  };

  const handleAddSkill = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = newSkill.trim().toLowerCase();
    if (clean && !skills.includes(clean)) {
      setSkills([...skills, clean]);
      setNewSkill('');
    }
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    setSkills(skills.filter(s => s !== skillToRemove));
  };

  const handleTestGitHubConnection = async () => {
    setIsTestingGitHub(true);
    setGithubTestResult(null);
    const tokenToTest = token.trim() || getCustomGitHubToken() || '';

    try {
      const headers: Record<string, string> = {
        'Accept': 'application/vnd.github.v3+json',
      };
      if (tokenToTest) {
        headers['Authorization'] = `token ${tokenToTest}`;
      }

      const res = await fetch('https://api.github.com/user', { headers });
      const rateLimitRemaining = parseInt(res.headers.get('x-ratelimit-remaining') || '0', 10);

      if (res.ok) {
        const data = await res.json();
        setGithubTestResult({
          success: true,
          login: data.login,
          rateLimitRemaining,
          message: `Successfully connected as @${data.login}! Authenticated quota: ${rateLimitRemaining} requests remaining.`,
        });
        if (data.login && !username) {
          setUsername(data.login);
        }
      } else {
        const err = await res.json().catch(() => ({}));
        setGithubTestResult({
          success: false,
          message: err.message || `GitHub returned HTTP ${res.status}: ${res.statusText}`,
        });
      }
    } catch (err: any) {
      setGithubTestResult({
        success: false,
        message: `Network error reaching GitHub API: ${err.message}`,
      });
    } finally {
      setIsTestingGitHub(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveMessage(null);

    // Save AI keys to local storage for instant client-side execution
    if (geminiKey.trim()) localStorage.setItem('issuetopr_gemini_key', geminiKey.trim());
    if (claudeKey.trim()) localStorage.setItem('issuetopr_claude_key', claudeKey.trim());
    if (openaiKey.trim()) localStorage.setItem('issuetopr_openai_key', openaiKey.trim());
    localStorage.setItem('issuetopr_preferred_ai', preferredModel);

    try {
      await onSaveSettings({
        github_token: token.trim() || undefined,
        github_username: username.trim(),
        auto_publish_pr: autoPublish,
        workspace_root: workspaceRoot.trim(),
        skills_profile: skills,
        gemini_api_key: geminiKey.trim() || undefined,
        anthropic_api_key: claudeKey.trim() || undefined,
        openai_api_key: openaiKey.trim() || undefined,
        custom_api_key: customKey.trim() || undefined,
        custom_endpoint: customEndpoint.trim() || undefined,
        preferred_ai_provider: preferredModel,
      });
      setSaveMessage('✓ Platform settings saved successfully.');
      if (token.trim()) {
        localStorage.setItem('issuetopr_github_token', token.trim());
        setToken('');
      }
      setTimeout(() => setSaveMessage(null), 5000);
    } catch (err: any) {
      setSaveMessage(`Settings saved locally. Note: ${err.message}`);
      setTimeout(() => setSaveMessage(null), 6000);
    } finally {
      setSaving(false);
    }
  };

  const handleSignOut = () => {
    logout();
  };

  const navSections = [
    { id: 'github' as SettingsSection, label: 'GitHub & Tokens', icon: Key },
    { id: 'ai' as SettingsSection, label: 'AI Intelligence', icon: Sparkles },
    { id: 'automation' as SettingsSection, label: 'Automation & Webhooks', icon: ShieldAlert },
    { id: 'skills' as SettingsSection, label: 'Skills & Weight Matrix', icon: Terminal },
    { id: 'team' as SettingsSection, label: 'Team & Private Repos', icon: Users },
    { id: 'workspace' as SettingsSection, label: 'Antigravity IDE', icon: Cpu },
    { id: 'account' as SettingsSection, label: 'Account & Security', icon: User },
  ];

  const hasConfiguredToken = Boolean(token.trim() || settings?.github_token_configured || getCustomGitHubToken());

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
            Settings & Integrations
          </h1>
          <p className="text-xs text-slate-500 dark:text-neutral-400 mt-1">
            Manage your GitHub credentials, AI models, automated pull request policies, and local workspace connections.
          </p>
        </div>

        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white dark:bg-white dark:hover:bg-neutral-200 dark:text-black font-bold text-xs shadow-md shadow-blue-600/20 active:scale-95 transition flex items-center gap-2 shrink-0 self-start sm:self-auto disabled:opacity-50"
        >
          {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          <span>{saving ? 'Saving...' : 'Save Settings'}</span>
        </button>
      </div>

      {/* Save Message Notification */}
      {saveMessage && (
        <div className="bg-[#0c101a] border border-emerald-500/30 text-emerald-300 rounded-xl p-3.5 text-xs flex items-center justify-between shadow-lg">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{saveMessage}</span>
          </div>
          <button onClick={() => setSaveMessage(null)} className="text-neutral-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Navigation Tabs Pill Bar */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 border-b border-slate-200 dark:border-white/10 no-scrollbar">
        {navSections.map((sec) => {
          const Icon = sec.icon;
          const isActive = activeSection === sec.id;
          return (
            <button
              key={sec.id}
              onClick={() => setActiveSection(sec.id)}
              className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-2 transition shrink-0 ${
                isActive
                  ? 'bg-blue-600 text-white font-bold shadow-md shadow-blue-600/20'
                  : 'bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-600 hover:text-slate-900 dark:bg-[#0c101a] dark:border-white/10 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-white/5'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{sec.label}</span>
            </button>
          );
        })}
      </div>

      {/* Section 1: GitHub & Tokens */}
      {activeSection === 'github' && (
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-5">
          <div className="flex items-center justify-between pb-3 border-b border-white/10">
            <div className="flex items-center gap-2.5">
              <Key className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white">GitHub API Credentials</h3>
            </div>
            <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-mono font-semibold flex items-center gap-1.5 ${
              hasConfiguredToken
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                : 'bg-amber-500/10 text-amber-300 border border-amber-500/20'
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${hasConfiguredToken ? 'bg-emerald-400' : 'bg-amber-400'}`} />
              {hasConfiguredToken ? 'Token Configured' : 'Needs Token'}
            </span>
          </div>

          <div className="space-y-4 text-xs">
            <div>
              <label className="block text-neutral-300 font-semibold mb-1.5">
                GitHub Personal Access Token (PAT)
              </label>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder={hasConfiguredToken ? '•••••••••••••••••••••••••••••••• (Configured - enter new to replace)' : 'ghp_... or github_pat_...'}
                className="w-full bg-[#05080f] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white/30 font-mono transition"
              />
              <p className="text-[11px] text-neutral-400 mt-1.5 leading-relaxed">
                Allows searching repositories with up to 5,000 requests/hour, posting assignment requests, creating branches, and opening verified pull requests.
              </p>
            </div>

            <div>
              <label className="block text-neutral-300 font-semibold mb-1.5">
                GitHub Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. Pushkar-Shahi"
                className="w-full bg-[#05080f] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white/30 font-mono transition"
              />
            </div>

            {/* Test GitHub Connection Action */}
            <div className="pt-2">
              <button
                type="button"
                onClick={handleTestGitHubConnection}
                disabled={isTestingGitHub}
                className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-white text-xs font-semibold flex items-center gap-2 transition active:scale-95 disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isTestingGitHub ? 'animate-spin' : ''}`} />
                <span>{isTestingGitHub ? 'Testing Connection...' : 'Test GitHub Connection'}</span>
              </button>

              {githubTestResult && (
                <div className={`mt-3 p-3 rounded-xl border text-xs flex items-start gap-2.5 ${
                  githubTestResult.success
                    ? 'bg-emerald-950/30 border-emerald-500/30 text-emerald-300'
                    : 'bg-rose-950/30 border-rose-500/30 text-rose-300'
                }`}>
                  {githubTestResult.success ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  )}
                  <div>
                    <span className="font-semibold">{githubTestResult.success ? 'Success' : 'Connection Failed'}:</span>
                    <p className="mt-0.5 text-[11px] leading-relaxed">{githubTestResult.message}</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Section 2: AI Intelligence & Models */}
      {activeSection === 'ai' && (
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-5">
          <div className="flex items-center gap-2.5 pb-3 border-b border-white/10">
            <Sparkles className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-bold text-white">AI Model Provider Configuration</h3>
          </div>

          <div className="space-y-4 text-xs">
            <div>
              <label className="block text-neutral-300 font-semibold mb-1.5">
                Preferred Primary AI Engine
              </label>
              <select
                value={preferredModel}
                onChange={(e) => setPreferredModel(e.target.value)}
                className="w-full bg-[#05080f] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-white/30 cursor-pointer"
              >
                <option value="gemini">Google Gemini 2.5 Flash (Fastest & Built-in Autonomous)</option>
                <option value="claude">Anthropic Claude 3.5 Sonnet (Advanced Architecture Reasoning)</option>
                <option value="openai">OpenAI GPT-4o (Empirical Code Generation)</option>
                <option value="custom">Local Runner / Ollama / Custom Endpoint</option>
              </select>
            </div>

            <div>
              <label className="block text-neutral-300 font-semibold mb-1.5">
                Google Gemini API Key
              </label>
              <input
                type="password"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder="AIzaSy... (leave blank to use system environment default)"
                className="w-full bg-[#05080f] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white/30 font-mono transition"
              />
            </div>

            <div>
              <label className="block text-neutral-300 font-semibold mb-1.5">
                Anthropic Claude API Key
              </label>
              <input
                type="password"
                value={claudeKey}
                onChange={(e) => setClaudeKey(e.target.value)}
                placeholder="sk-ant-... (optional)"
                className="w-full bg-[#05080f] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white/30 font-mono transition"
              />
            </div>

            <div>
              <label className="block text-neutral-300 font-semibold mb-1.5">
                OpenAI API Key
              </label>
              <input
                type="password"
                value={openaiKey}
                onChange={(e) => setOpenaiKey(e.target.value)}
                placeholder="sk-... (optional)"
                className="w-full bg-[#05080f] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white/30 font-mono transition"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              <div>
                <label className="block text-neutral-300 font-semibold mb-1.5">
                  Custom / Ollama Endpoint URL
                </label>
                <input
                  type="text"
                  value={customEndpoint}
                  onChange={(e) => setCustomEndpoint(e.target.value)}
                  placeholder="http://localhost:11434/v1"
                  className="w-full bg-[#05080f] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white/30 font-mono transition"
                />
              </div>
              <div>
                <label className="block text-neutral-300 font-semibold mb-1.5">
                  Custom Provider API Key
                </label>
                <input
                  type="password"
                  value={customKey}
                  onChange={(e) => setCustomKey(e.target.value)}
                  placeholder="Optional token for custom endpoint"
                  className="w-full bg-[#05080f] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white/30 font-mono transition"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Section 3: Automation & PRs + Real-Time Webhooks (Pro) */}
      {activeSection === 'automation' && (
        <div className="space-y-6">
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-5">
          <div className="flex items-center gap-2.5 pb-3 border-b border-white/10">
            <ShieldAlert className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">Automated PR & Runner Policies</h3>
          </div>

          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1 text-xs">
              <span className="font-semibold text-slate-900 dark:text-white">
                Auto-Publish Pull Requests upon Successful Validation
              </span>
              <p className="text-slate-500 dark:text-neutral-400 leading-relaxed">
                When enabled, once all test runs and AST diff security checks pass with exit code 0, the platform will autonomously push to your fork and publish the PR without an extra per-PR manual confirmation.
              </p>
              <div className="bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl p-3 mt-2 text-[11px] text-slate-600 dark:text-neutral-400">
                Safety Guarantee: Unresolved policy checks, non-OSI licenses, or test failures always block PR creation regardless of this toggle.
              </div>
            </div>

            <label className="relative inline-flex items-center cursor-pointer shrink-0 mt-1">
              <input
                type="checkbox"
                checked={autoPublish}
                onChange={(e) => setAutoPublish(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-neutral-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-black after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600 peer-checked:after:bg-white"></div>
            </label>
          </div>
        </div>

        {/* Pro Real-Time Discovery & Repository Webhooks */}
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100 dark:border-white/10">
            <div className="flex items-center gap-2.5">
              <Webhook className="w-4 h-4 text-blue-500" />
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  Priority Real-Time Discovery & GitHub Webhooks
                </h3>
                <p className="text-[11px] text-slate-500 dark:text-neutral-400">
                  Receive instant issue/PR updates instead of waiting for the standard 2-hour crawl cycle.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={handlePriorityDiscovery}
              disabled={prioritySyncing}
              className="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-sm transition active:scale-95 disabled:opacity-50"
            >
              <Zap className={`w-3.5 h-3.5 ${prioritySyncing ? 'animate-pulse' : ''}`} />
              <span>{prioritySyncing ? 'Priority Syncing...' : 'Run Priority Sync Now'}</span>
            </button>
          </div>

          <div className="p-3 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 text-[11px] text-slate-600 dark:text-neutral-400">
            Payload URL: <code className="font-mono text-slate-900 dark:text-white">{typeof window !== 'undefined' ? `${window.location.origin}/api/v1/webhooks/github` : '/api/v1/webhooks/github'}</code>
          </div>

          {webhookTierLocked ? (
            <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-500/30 text-xs text-amber-800 dark:text-amber-300">
              Real-time repository webhook subscriptions require <strong>Pro Developer (₹100/mo)</strong> or <strong>Engineering Team</strong>.
            </div>
          ) : (
            <>
              <form onSubmit={handleCreateWebhook} className="flex flex-col sm:flex-row gap-2">
                <input
                  type="text"
                  value={newWebhookRepo}
                  onChange={(e) => setNewWebhookRepo(e.target.value)}
                  placeholder="owner/repo (e.g. kornia/kornia or org/private-repo)"
                  className="flex-1 bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-white font-mono"
                />
                <button
                  type="submit"
                  disabled={creatingWebhook || !newWebhookRepo.trim()}
                  className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 transition active:scale-95 disabled:opacity-50"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>{creatingWebhook ? 'Creating...' : 'Create Webhook'}</span>
                </button>
              </form>

              {webhooks.length > 0 && (
                <div className="divide-y divide-slate-100 dark:divide-white/10">
                  {webhooks.map((wh) => (
                    <div key={wh.id} className="py-3 flex flex-wrap items-center justify-between gap-3">
                      <div className="space-y-0.5 min-w-0">
                        <div className="text-xs font-bold text-slate-900 dark:text-white">{wh.repo_full_name}</div>
                        <div className="text-[11px] font-mono text-slate-500 dark:text-neutral-400">
                          Secret: {wh.webhook_secret.slice(0, 12)}••• • {wh.deliveries_count} deliveries
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            navigator.clipboard.writeText(wh.webhook_secret);
                            setCopiedSecretId(wh.id);
                            setTimeout(() => setCopiedSecretId(null), 2000);
                          }}
                          className="px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-white/5 dark:hover:bg-white/10 text-[11px] font-semibold text-slate-700 dark:text-neutral-200 flex items-center gap-1"
                        >
                          {copiedSecretId === wh.id ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                          <span>{copiedSecretId === wh.id ? 'Copied' : 'Copy Secret'}</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteWebhook(wh.id)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
        </div>
      )}

      {/* Section 4: Toolbox Skills Profile + Custom Weighting Matrix (Pro) */}
      {activeSection === 'skills' && (
        <div className="space-y-6">
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-5">
          <div className="flex items-center gap-2.5 pb-3 border-b border-white/10">
            <Terminal className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">Configurable Technology Stack Skills</h3>
          </div>

          <div className="space-y-3">
            <p className="text-xs text-slate-500 dark:text-neutral-400">
              Issues matching these frameworks and languages receive higher suitability and priority rankings:
            </p>

            <form onSubmit={handleAddSkill} className="flex gap-2">
              <input
                type="text"
                value={newSkill}
                onChange={(e) => setNewSkill(e.target.value)}
                placeholder="Add skill or language (e.g. Next.js, Rust, Go, PyTorch, Docker)..."
                className="flex-1 bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-white placeholder-neutral-500 focus:outline-none focus:border-white/30 transition"
              />
              <button
                type="submit"
                className="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition flex items-center gap-1.5 active:scale-95"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add</span>
              </button>
            </form>

            <div className="flex flex-wrap gap-2 pt-2">
              {skills.map(s => (
                <span
                  key={s}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 text-xs font-mono text-slate-900 dark:text-white shadow-sm"
                >
                  <span>{s}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveSkill(s)}
                    className="text-neutral-400 hover:text-rose-400 transition ml-1"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Custom Skill & Tag Weighting Matrix */}
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100 dark:border-white/10">
            <div className="flex items-center gap-2.5">
              <Sliders className="w-4 h-4 text-indigo-500" />
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  Custom Skill & Tag Weighting Matrix
                </h3>
                <p className="text-[11px] text-slate-500 dark:text-neutral-400">
                  Tune priority multipliers (0.5x – 3.0x) and re-rank open issues in your inbox.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleSaveMatrixAndRescore}
              disabled={matrixSaving}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-sm transition active:scale-95 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${matrixSaving ? 'animate-spin' : ''}`} />
              <span>{matrixSaving ? 'Re-Ranking...' : 'Save Matrix & Re-Rank Issues'}</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className="space-y-2.5">
              <div className="text-[11px] font-mono uppercase font-bold text-slate-500 dark:text-neutral-400">
                Skill Multipliers
              </div>
              {skills.slice(0, 8).map((s) => {
                const w = Number(skillWeights[s.toLowerCase()] ?? 1.0);
                return (
                  <div key={s} className="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10">
                    <span className="text-xs font-mono font-semibold text-slate-800 dark:text-neutral-200">{s}</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="range"
                        min={0.5}
                        max={3.0}
                        step={0.25}
                        value={w}
                        onChange={(e) => setSkillWeights((prev) => ({ ...prev, [s.toLowerCase()]: Number(e.target.value) }))}
                        className="w-24 accent-indigo-600"
                      />
                      <span className="text-[11px] font-mono font-bold text-indigo-600 dark:text-indigo-400 w-9 text-right">
                        {w.toFixed(1)}x
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="space-y-2.5">
              <div className="text-[11px] font-mono uppercase font-bold text-slate-500 dark:text-neutral-400">
                Issue Label / Tag Multipliers
              </div>
              {DEFAULT_TAG_KEYS.map((tag) => {
                const w = Number(tagWeights[tag] ?? 1.0);
                return (
                  <div key={tag} className="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10">
                    <span className="text-xs font-semibold text-slate-800 dark:text-neutral-200">{tag}</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="range"
                        min={0.5}
                        max={3.0}
                        step={0.25}
                        value={w}
                        onChange={(e) => setTagWeights((prev) => ({ ...prev, [tag]: Number(e.target.value) }))}
                        className="w-24 accent-emerald-600"
                      />
                      <span className="text-[11px] font-mono font-bold text-emerald-600 dark:text-emerald-400 w-9 text-right">
                        {w.toFixed(1)}x
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        </div>
      )}

      {/* Section 5: Team Seats, Private Repos & RBAC Governance */}
      {activeSection === 'team' && (
        <TeamGovernancePanel settings={settings} onSettingsUpdated={onSettingsUpdated} />
      )}

      {/* Section 5: Antigravity IDE Integration */}
      {activeSection === 'workspace' && (
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-5">
          <div className="flex items-center gap-2.5 pb-3 border-b border-white/10">
            <Cpu className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-bold text-white">Google Antigravity Desktop & CLI Integration</h3>
          </div>

          <div className="space-y-3 text-xs text-neutral-300">
            <div className="flex items-center justify-between bg-[#05080f] p-3.5 rounded-xl border border-white/10">
              <span>Standalone Desktop App:</span>
              <span className="font-semibold text-emerald-400 font-mono flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>Installed (/Applications/Antigravity.app)</span>
              </span>
            </div>

            <div className="flex items-center justify-between bg-[#05080f] p-3.5 rounded-xl border border-white/10">
              <span>Antigravity CLI (agy):</span>
              <span className="font-semibold text-emerald-400 font-mono flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>Detected (~/.local/bin/agy)</span>
              </span>
            </div>

            <div>
              <label className="block text-neutral-300 font-semibold mb-1.5">
                Workspace Root Directory
              </label>
              <input
                type="text"
                value={workspaceRoot}
                onChange={(e) => setWorkspaceRoot(e.target.value)}
                className="w-full bg-[#05080f] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white font-mono focus:outline-none focus:border-white/30 transition"
              />
            </div>
          </div>
        </div>
      )}

      {/* Section 6: Account & Security */}
      {activeSection === 'account' && (
        <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-5 sm:p-6 shadow-sm dark:shadow-xl space-y-5">
          <div className="flex items-center gap-2.5 pb-3 border-b border-white/10">
            <User className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-white">Account Profile & Session Management</h3>
          </div>

          <div className="space-y-4 text-xs">
            <div className="bg-[#05080f] p-4 rounded-xl border border-white/10 flex items-center justify-between">
              <div>
                <span className="font-bold text-white text-sm">Authenticated User</span>
                <p className="text-neutral-400 text-xs mt-0.5 font-mono">{username || 'Developer'}</p>
              </div>
              <span className="px-3 py-1 rounded-full text-[10px] font-mono bg-blue-600/20 text-blue-400 border border-blue-500/30 font-bold">
                Owner / Admin
              </span>
            </div>

            <div className="pt-2">
              <button
                type="button"
                onClick={handleSignOut}
                className="px-4 py-2.5 rounded-xl bg-rose-950/40 hover:bg-rose-950/70 text-rose-300 border border-rose-800/50 text-xs font-semibold flex items-center gap-2 transition active:scale-95"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Sign Out of Platform</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SettingsView;