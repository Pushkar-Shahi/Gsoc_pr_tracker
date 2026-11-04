import React, { useState, useEffect, useRef } from 'react';
import { Building2, ChevronDown, Check, Plus, Users, Shield, Sparkles } from 'lucide-react';
import { Organization } from '../types';
import { fetchOrganizations, switchOrganization } from '../api';
import { CreateOrganizationModal } from './CreateOrganizationModal';

interface OrganizationSwitcherProps {
  onOrganizationChanged?: (org: Organization) => void;
}

export const OrganizationSwitcher: React.FC<OrganizationSwitcherProps> = ({ onOrganizationChanged }) => {
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
        className="flex items-center gap-2 h-9 px-3 rounded-xl bg-neutral-900/80 hover:bg-neutral-800/90 border border-white/10 hover:border-indigo-500/30 text-neutral-200 transition active:scale-95 shadow-lg backdrop-blur-xl"
        title="Switch Organization / Team Workspace"
      >
        <div className="w-5 h-5 rounded-lg bg-gradient-to-br from-indigo-500 to-cyan-500 p-0.5 shrink-0 shadow-sm">
          <div className="w-full h-full bg-[#0a0a0f] rounded-[6px] flex items-center justify-center">
            <Building2 className="w-3 h-3 text-cyan-300" />
          </div>
        </div>
        <span className="text-xs font-semibold text-white max-w-[130px] truncate">
          {activeOrg?.name || 'My Workspace'}
        </span>
        <ChevronDown className={`w-3.5 h-3.5 text-neutral-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Liquid Glass Dropdown Menu */}
      {isOpen && (
        <div className="absolute left-0 mt-2 w-72 rounded-2xl bg-[#090909]/95 border border-white/15 p-2 shadow-2xl shadow-indigo-950/50 backdrop-blur-2xl z-50 space-y-1 animate-fade-in">
          {/* Header */}
          <div className="px-3 py-2 flex items-center justify-between border-b border-white/10">
            <span className="text-[11px] font-bold uppercase tracking-wider text-neutral-400 font-mono">
              Workspaces & Orgs
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-500/30 font-mono">
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
                      ? 'bg-gradient-to-r from-indigo-950/70 to-neutral-900 border border-indigo-500/40 text-white'
                      : 'hover:bg-neutral-800/60 border border-transparent text-neutral-300'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold shrink-0 ${
                      isActive
                        ? 'bg-gradient-to-br from-indigo-500 to-cyan-500 text-white shadow-md shadow-indigo-500/30'
                        : 'bg-neutral-800 text-neutral-300 group-hover:bg-neutral-700'
                    }`}>
                      {org.name.slice(0, 1).toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-bold truncate text-white">{org.name}</span>
                        {org.is_personal && (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-neutral-800 text-neutral-400 font-mono">
                            Personal
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-neutral-400">
                        <span className="capitalize text-indigo-300">{org.role}</span>
                        <span>&bull;</span>
                        <span>{org.member_count} {org.member_count === 1 ? 'member' : 'members'}</span>
                      </div>
                    </div>
                  </div>
                  {isActive && <Check className="w-4 h-4 text-cyan-400 shrink-0" />}
                </button>
              );
            })}
          </div>

          {/* Create Organization Action */}
          <div className="pt-1 border-t border-white/10">
            <button
              onClick={() => {
                setIsOpen(false);
                setShowCreateModal(true);
              }}
              className="w-full flex items-center gap-2 p-2 rounded-xl text-xs font-semibold text-indigo-300 hover:text-white hover:bg-indigo-950/40 border border-transparent hover:border-indigo-500/30 transition"
            >
              <Plus className="w-3.5 h-3.5 text-cyan-400" />
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
