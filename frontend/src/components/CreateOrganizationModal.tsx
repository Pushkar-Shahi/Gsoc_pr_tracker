import React, { useState } from 'react';
import { Building2, X, Plus, Sparkles, Check, AlertCircle } from 'lucide-react';
import { Organization } from '../types';
import { createOrganization, switchOrganization } from '../api';

interface CreateOrganizationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOrganizationCreated: (org: Organization) => void;
}

export const CreateOrganizationModal: React.FC<CreateOrganizationModalProps> = ({
  isOpen,
  onClose,
  onOrganizationCreated
}) => {
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setName(val);
    if (!slug || slug === name.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 30)) {
      setSlug(val.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 30));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Please enter an organization name.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const created = await createOrganization(name.trim(), slug.trim() || undefined);
      // Automatically switch to the newly created organization
      await switchOrganization(created.id);
      onOrganizationCreated({ ...created, is_active: true });
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to create organization');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-xl animate-fade-in">
      {/* Ambient liquid glow behind the modal */}
      <div className="absolute w-96 h-96 rounded-full bg-indigo-600/20 blur-3xl pointer-events-none" />
      <div className="absolute w-80 h-80 rounded-full bg-cyan-600/15 blur-3xl pointer-events-none translate-x-24 -translate-y-16" />

      <div className="relative w-full max-w-md rounded-2xl bg-[#090909]/90 border border-white/15 p-6 shadow-2xl shadow-indigo-950/40 space-y-5 backdrop-blur-2xl">
        {/* Modal Header */}
        <div className="flex items-center justify-between pb-3 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-500 p-0.5 shadow-lg shadow-indigo-500/25">
              <div className="w-full h-full bg-[#0a0a0f] rounded-[10px] flex items-center justify-center">
                <Building2 className="w-4 h-4 text-cyan-300" />
              </div>
            </div>
            <div>
              <h3 className="text-base font-bold text-white tracking-tight">Create Organization</h3>
              <p className="text-[11px] text-neutral-400">Collaborate with your team on shared repositories</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-neutral-400 hover:text-white hover:bg-white/10 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {error && (
          <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/30 flex items-center gap-2 text-xs text-rose-300">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-neutral-300">Organization Name</label>
            <input
              type="text"
              value={name}
              onChange={handleNameChange}
              placeholder="e.g. Acme Engineering or OpenSource Guild"
              autoFocus
              className="w-full px-3.5 py-2.5 rounded-xl bg-[#030303] border border-white/15 text-white placeholder-neutral-600 text-sm focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/50 transition"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-neutral-300">Workspace Slug</label>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-neutral-500">app.dev/</span>
              <input
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="acme-engineering"
                className="w-full px-3.5 py-2 rounded-xl bg-[#030303] border border-white/15 text-white font-mono text-xs placeholder-neutral-600 focus:outline-none focus:border-indigo-400 transition"
              />
            </div>
          </div>

          {/* Included Features preview */}
          <div className="p-3 rounded-xl bg-indigo-950/20 border border-indigo-500/20 text-xs text-neutral-300 space-y-1">
            <div className="flex items-center gap-1.5 text-indigo-300 font-semibold">
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              <span>Multi-Tenant Worktree Isolation Included</span>
            </div>
            <p className="text-[11px] text-neutral-400">
              Each organization gets isolated Git worktrees, independent test fleets, dedicated runner queues, and role-based permissions.
            </p>
          </div>

          <div className="pt-2 flex items-center justify-end gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-neutral-900 hover:bg-neutral-800 text-neutral-300 border border-white/10 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !name.trim()}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-gradient-to-r from-indigo-500 to-cyan-500 hover:from-indigo-400 hover:to-cyan-400 text-white shadow-lg shadow-indigo-500/25 transition disabled:opacity-50"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{loading ? 'Creating...' : 'Create & Switch Workspace'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
