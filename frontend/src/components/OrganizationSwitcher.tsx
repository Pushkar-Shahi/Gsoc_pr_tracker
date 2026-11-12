import React, { useState, useEffect, useRef } from 'react';
import { Building2, ChevronDown, Check, Plus, Users, Shield, Sparkles } from 'lucide-react';
import { Organization } from '../types';
import { fetchOrganizations, switchOrganization } from '../api';
import { CreateOrganizationModal } from './CreateOrganizationModal';

interface OrganizationSwitcherProps {
  onOrganizationChanged?: (org: Organization) => void;
  onOpenTeamSettings?: () => void;
}

export const OrganizationSwitcher: React.FC<OrganizationSwitcherProps> = ({
  onOrganizationChanged,
  onOpenTeamSettings,
}) => {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const loadOrganizations = async () => {
    try {
      const orgs = await fetchOrganizations();
      setOrganizations(orgs);
    } catch (err) {
      console.error('Failed to load organizations:', err);
    }
  };

  useEffect(() => {
    loadOrganizations();
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const activeOrg = organizations.find(o => o.is_active) || organizations[0];

  const handleSelectOrg = async (org: Organization) => {
    if (org.is_active) {
      setIsOpen(false);
      return;
    }

    setLoading(true);
    try {
      await switchOrganization(org.id);
      setOrganizations(prev =>
        prev.map(o => ({ ...o, is_active: o.id === org.id }))
      );
      setIsOpen(false);
      if (onOrganizationChanged) {
        onOrganizationChanged({ ...org, is_active: true });
      }
      // Reload dashboard data under new tenant
      window.location.reload();
    } catch (err) {
      console.error('Failed to switch workspace:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreated = (newOrg: Organization) => {
    setOrganizations(prev => [
      ...prev.map(o => ({ ...o, is_active: false })),
      newOrg
    ]);
    if (onOrganizationChanged) {
      onOrganizationChanged(newOrg);
    }
    window.location.reload();
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Switcher Pill Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2.5 h-9 px-3.5 rounded-full bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-800 dark:bg-white/5 dark:hover:bg-white/10 dark:border-white/10 dark:text-white text-xs font-medium transition active:scale-95 shadow-sm"
        title="Switch Organization / Team Workspace"
      >
        <svg className="w-4 h-4 fill-current shrink-0 text-slate-700 dark:text-white" viewBox="0 0 24 24">
          <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
        </svg>
        <span className="max-w-[160px] truncate font-medium text-slate-800 dark:text-neutral-200">
          {activeOrg?.name || 'My Workspace'}
        </span>
        <ChevronDown className={`w-3.5 h-3.5 text-slate-500 dark:text-neutral-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Liquid Glass Dropdown Menu */}
      {isOpen && (
        <div className="absolute left-0 mt-2 w-72 rounded-2xl bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/15 p-2 shadow-2xl z-50 space-y-1 animate-dropdown">
          {/* Header */}
          <div className="px-3 py-2 flex items-center justify-between border-b border-slate-200 dark:border-white/10">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-neutral-400 font-mono">
              Workspaces & Orgs
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-100 text-indigo-700 border border-indigo-200 dark:bg-indigo-950 dark:text-indigo-300 dark:border-indigo-500/30 font-mono">
              {organizations.length} Total
            </span>
          </div>

          {/* Org List */}
          <div className="max-h-56 overflow-y-auto space-y-1 py-1">
            {organizations.map(org => {
              const isActive = org.is_active;
              return (
                <button
                  key={org.id}
                  onClick={() => handleSelectOrg(org)}
                  disabled={loading}
                  className={`w-full flex items-center justify-between p-2.5 rounded-xl text-left transition group ${
                    isActive
                      ? 'bg-indigo-50 border border-indigo-200 text-indigo-950 dark:bg-gradient-to-r dark:from-indigo-950/70 dark:to-neutral-900 dark:border-indigo-500/40 dark:text-white'
                      : 'hover:bg-slate-100 dark:hover:bg-neutral-800/60 border border-transparent text-slate-700 dark:text-neutral-300'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold shrink-0 ${
                      isActive
                        ? 'bg-gradient-to-br from-indigo-500 to-cyan-500 text-white shadow-md shadow-indigo-500/30'
                        : 'bg-slate-200 text-slate-700 dark:bg-neutral-800 dark:text-neutral-300 group-hover:bg-slate-300 dark:group-hover:bg-neutral-700'
                    }`}>
                      {org.name.slice(0, 1).toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-bold truncate text-slate-900 dark:text-white">{org.name}</span>
                        {org.is_personal && (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-slate-200 text-slate-600 dark:bg-neutral-800 dark:text-neutral-400 font-mono">
                            Personal
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-slate-500 dark:text-neutral-400">
                        <span className="capitalize text-indigo-600 dark:text-indigo-300">{org.role}</span>
                        <span>&bull;</span>
                        <span>{org.member_count} {org.member_count === 1 ? 'member' : 'members'}</span>
                      </div>
                    </div>
                  </div>
                  {isActive && <Check className="w-4 h-4 text-cyan-600 dark:text-cyan-400 shrink-0" />}
                </button>
              );
            })}
          </div>

          {/* Create Organization & Team Governance Actions */}
          <div className="pt-1 border-t border-slate-200 dark:border-white/10 space-y-1">
            {onOpenTeamSettings && (
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false);
                  onOpenTeamSettings();
                }}
                className="w-full flex items-center gap-2 p-2 rounded-xl text-xs font-semibold text-slate-700 dark:text-neutral-200 hover:bg-slate-100 dark:hover:bg-white/10 transition"
              >
                <Users className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                <span>Team Seats, Private Repos & RBAC</span>
              </button>
            )}
            <button
              onClick={() => {
                setIsOpen(false);
                setShowCreateModal(true);
              }}
              className="w-full flex items-center gap-2 p-2 rounded-xl text-xs font-semibold text-indigo-600 dark:text-indigo-300 hover:text-indigo-700 dark:hover:text-white hover:bg-indigo-50 dark:hover:bg-indigo-950/40 border border-transparent hover:border-indigo-200 dark:hover:border-indigo-500/30 transition"
            >
              <Plus className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400" />
              <span>Create New Organization</span>
            </button>
          </div>
        </div>
      )}

      {/* Create Org Modal */}
      <CreateOrganizationModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onOrganizationCreated={handleCreated}
      />
    </div>
  );
};

