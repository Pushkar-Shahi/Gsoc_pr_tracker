import React, { useState } from 'react';
import { 
  Settings, Key, Terminal, Shield, Folder, Check, 
  AlertTriangle, Save, Plus, X, ShieldAlert, RefreshCw
} from 'lucide-react';
import { PlatformSettings } from '../types';

interface SettingsViewProps {
  settings: PlatformSettings | null;
  onSaveSettings: (updated: Partial<PlatformSettings> & { github_token?: string }) => Promise<void>;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  settings,
  onSaveSettings,
}) => {
  const [token, setToken] = useState('');
  const [username, setUsername] = useState(settings?.github_username || '');
  const [autoPublish, setAutoPublish] = useState(settings?.auto_publish_pr || false);
  const [workspaceRoot, setWorkspaceRoot] = useState(settings?.workspace_root || '');
  const [skills, setSkills] = useState<string[]>(settings?.skills_profile || []);
  const [newSkill, setNewSkill] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const handleAddSkill = (e: React.FormEvent) => {
    e.preventDefault();
    if (newSkill.trim() && !skills.includes(newSkill.trim().toLowerCase())) {
      setSkills([...skills, newSkill.trim().toLowerCase()]);
      setNewSkill('');
    }
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    setSkills(skills.filter(s => s !== skillToRemove));
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveMessage(null);
    try {
      await onSaveSettings({
        github_token: token.trim() || undefined,
        github_username: username.trim(),
        auto_publish_pr: autoPublish,
        workspace_root: workspaceRoot.trim(),
        skills_profile: skills,
      });
      setSaveMessage('Platform settings saved successfully.');
      setToken('');
    } catch (err: any) {
      setSaveMessage(`Error saving settings: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto animate-fade-in-up">
      <div>
        <h2 className="text-xl font-extrabold text-white">Platform Settings & Security Profile</h2>
        <p className="text-xs text-neutral-400 mt-1">
          Configure GitHub API credentials, automated pull request publication policies, and Antigravity workspace integration.
        </p>
      </div>

      {saveMessage && (
        <div className="bg-[#080808] border border-white/20 rounded-xl p-3.5 text-xs text-white flex items-center gap-2">
          <Check className="w-4 h-4 text-white shrink-0" />
          <span>{saveMessage}</span>
        </div>
      )}

      {/* GitHub Authentication Card */}
      <div className="bg-[#080808] border border-white/10 rounded-2xl p-4 sm:p-6 shadow-xl space-y-4">
        <div className="flex items-center gap-2.5 pb-3 border-b border-white/10">
          <Key className="w-4 h-4 text-white" />
          <h3 className="text-sm font-semibold text-white">GitHub API Credentials</h3>
        </div>

        <div className="space-y-4 text-xs">
          <div>
            <label className="block text-neutral-300 font-medium mb-1.5">
              Personal Access Token (PAT)
            </label>
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={settings?.github_token_configured ? '•••••••••••••••••••••••• (Configured)' : 'Enter GitHub Personal Access Token (classic or fine-grained)...'}
              className="w-full min-h-[44px] bg-[#000000] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white font-mono transition"
            />
            <p className="text-[11px] text-neutral-500 mt-1.5">
              Required for authenticated discovery (5,000 req/hr), posting approved assignment comments, and publishing pull requests.
            </p>
          </div>

          <div>
            <label className="block text-neutral-300 font-medium mb-1.5">
              GitHub Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. your-github-username"
              className="w-full min-h-[44px] bg-[#000000] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white transition"
            />
          </div>
        </div>
      </div>

      {/* Automated PR Publishing Policy Toggle */}
      <div className="bg-[#080808] border border-white/10 rounded-2xl p-4 sm:p-6 shadow-xl space-y-4">
        <div className="flex items-center gap-2.5 pb-3 border-b border-white/10">
          <ShieldAlert className="w-4 h-4 text-white" />
          <h3 className="text-sm font-semibold text-white">Automated PR Publishing Permission</h3>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1 text-xs">
            <span className="font-semibold text-white">
              Auto-Publish Pull Request upon successful validation
            </span>
            <p className="text-neutral-400 leading-relaxed">
              When enabled, once all tests and diff security scans pass with exit code 0, the platform will automatically push to your fork and publish a PR without requiring an extra per-PR confirmation.
            </p>
            <div className="bg-[#000000] border border-white/10 rounded-lg p-2.5 mt-2 text-[11px] text-neutral-300">
              Note: Unresolved policy questions, missing licenses, or failed tests will always block publication regardless of this setting.
            </div>
          </div>

          <label className="relative inline-flex items-center cursor-pointer shrink-0 mt-1">
            <input
              type="checkbox"
              checked={autoPublish}
              onChange={(e) => setAutoPublish(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-neutral-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-black after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-white peer-checked:after:bg-black"></div>
          </label>
        </div>
      </div>

      {/* Skills Profile Tags */}
      <div className="bg-[#080808] border border-white/10 rounded-2xl p-4 sm:p-6 shadow-xl space-y-4">
        <div className="flex items-center gap-2.5 pb-3 border-b border-white/10">
          <Terminal className="w-4 h-4 text-white" />
          <h3 className="text-sm font-semibold text-white">Configurable Toolbox Skills Profile</h3>
        </div>

        <div className="space-y-3">
          <p className="text-xs text-neutral-400">
            Issues matching these technologies receive higher suitability scores in the Issue Inbox:
          </p>

          <form onSubmit={handleAddSkill} className="flex gap-2">
            <input
              type="text"
              value={newSkill}
              onChange={(e) => setNewSkill(e.target.value)}
              placeholder="Add technology or framework (e.g. Next.js, Rust, Go, PyTorch)..."
              className="flex-1 min-h-[44px] bg-[#000000] border border-white/10 rounded-xl px-3.5 py-2 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white transition"
            />
            <button
              type="submit"
              className="min-h-[44px] px-4 py-2 rounded-xl bg-[#111111] hover:bg-[#1a1a1a] text-white text-xs font-semibold border border-white/10 transition flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add</span>
            </button>
          </form>

          <div className="flex flex-wrap gap-2 pt-2">
            {skills.map(s => (
              <span
                key={s}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-[#111111] border border-white/10 text-xs font-mono text-white"
              >
                <span>{s}</span>
                <button
                  type="button"
                  onClick={() => handleRemoveSkill(s)}
                  className="hover:text-neutral-400 transition"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Antigravity Desktop Installation Info */}
      <div className="bg-[#080808] border border-white/10 rounded-2xl p-4 sm:p-6 shadow-xl space-y-4">
        <div className="flex items-center gap-2.5 pb-3 border-b border-white/10">
          <Terminal className="w-4 h-4 text-white" />
          <h3 className="text-sm font-semibold text-white">Google Antigravity Desktop Integration</h3>
        </div>

        <div className="space-y-3 text-xs text-neutral-300">
          <div className="flex items-center justify-between bg-[#000000] p-3 rounded-xl border border-white/10">
            <span>Standalone Desktop App:</span>
            <span className="font-semibold text-white font-mono">
              {settings?.detected_antigravity_installed ? 'Installed (/Applications/Antigravity.app)' : 'Ready'}
            </span>
          </div>

          <div className="flex items-center justify-between bg-[#000000] p-3 rounded-xl border border-white/10">
            <span>Antigravity CLI (agy):</span>
            <span className="font-semibold text-white font-mono">
              {settings?.detected_agy_cli ? 'Detected (~/.local/bin/agy)' : 'Supported'}
            </span>
          </div>

          <div>
            <label className="block text-neutral-300 font-medium mb-1.5">
              Workspace Root Directory
            </label>
            <input
              type="text"
              value={workspaceRoot}
              onChange={(e) => setWorkspaceRoot(e.target.value)}
              className="w-full min-h-[44px] bg-[#000000] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white font-mono focus:outline-none focus:border-white transition"
            />
          </div>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end pt-2 pb-6">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="min-h-[44px] px-8 py-3 rounded-xl bg-white hover:bg-neutral-200 text-black font-bold text-xs shadow-lg active:scale-95 transition flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          <span>{saving ? 'Saving Settings...' : 'Save Settings'}</span>
        </button>
      </div>
    </div>
  );
};

export default SettingsView;
