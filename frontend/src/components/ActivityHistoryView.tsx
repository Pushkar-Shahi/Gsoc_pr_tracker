import React, { useState } from 'react';
import { Search, FileSpreadsheet, FileCode, Shield } from 'lucide-react';
import { AuditLog } from '../types';
import { exportAuditLogs } from '../api';
import { EnterpriseSSOModal } from './EnterpriseSSOModal';

interface ActivityHistoryViewProps {
  logs: AuditLog[];
}

export const ActivityHistoryView: React.FC<ActivityHistoryViewProps> = ({ logs }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [isExporting, setIsExporting] = useState<string | null>(null);
  const [isSSOModalOpen, setIsSSOModalOpen] = useState(false);

  const handleExport = async (format: 'csv' | 'json') => {
    try {
      setIsExporting(format);
      await exportAuditLogs(format);
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    } finally {
      setIsExporting(null);
    }
  };

  const filteredLogs = logs.filter(log => {
    const matchesSearch = !searchTerm || 
      log.action.toLowerCase().includes(searchTerm.toLowerCase()) ||
      JSON.stringify(log.details).toLowerCase().includes(searchTerm.toLowerCase());
    const matchesAction = !filterAction || log.action === filterAction;
    return matchesSearch && matchesAction;
  });

  const getActionBadgeColor = (action: string) => {
    if (action.includes('PR_PUBLISHED')) return 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-500/20 dark:text-purple-300 dark:border-purple-500/30 font-bold';
    if (action.includes('VALIDATION')) return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/20 dark:text-emerald-300 dark:border-emerald-500/30';
    if (action.includes('ASSIGNMENT')) return 'bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-500/20 dark:text-cyan-300 dark:border-cyan-500/30';
    if (action.includes('WORKSPACE')) return 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-500/30';
    return 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-white/5 dark:text-neutral-300 dark:border-white/10';
  };

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-extrabold text-slate-900 dark:text-white">Immutable Activity Audit Trail</h2>
            <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-800 border border-slate-200 dark:bg-white/10 dark:text-white dark:border-white/20">
              {logs.length} Events
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-neutral-400 mt-1">
            Cryptographically stored timestamped record of every workflow transition, decision, and external GitHub interaction.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => handleExport('csv')}
            disabled={isExporting !== null}
            className="px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 hover:text-slate-900 dark:bg-white/5 dark:hover:bg-white/10 dark:border-white/10 dark:text-neutral-300 dark:hover:text-white text-xs font-semibold flex items-center gap-1.5 transition active:scale-95 disabled:opacity-50"
            title="Download audit logs in RFC 4180 CSV format"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
            <span>{isExporting === 'csv' ? 'Exporting...' : 'Export CSV'}</span>
          </button>

          <button
            onClick={() => handleExport('json')}
            disabled={isExporting !== null}
            className="px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 hover:text-slate-900 dark:bg-white/5 dark:hover:bg-white/10 dark:border-white/10 dark:text-neutral-300 dark:hover:text-white text-xs font-semibold flex items-center gap-1.5 transition active:scale-95 disabled:opacity-50"
            title="Download logs in SIEM NDJSON format for Splunk/Datadog"
          >
            <FileCode className="w-3.5 h-3.5 text-cyan-400" />
            <span>{isExporting === 'json' ? 'Exporting...' : 'Export SIEM'}</span>
          </button>

          <button
            onClick={() => setIsSSOModalOpen(true)}
            className="px-3.5 py-2 rounded-xl bg-purple-50 hover:bg-purple-100 border border-purple-200 text-purple-700 dark:bg-purple-950/40 dark:border-purple-500/30 dark:hover:bg-purple-900/40 dark:text-purple-300 text-xs font-semibold flex items-center gap-1.5 transition active:scale-95 shadow-sm"
            title="Configure SAML 2.0 / OIDC Identity Provider"
          >
            <Shield className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
            <span>Enterprise SSO</span>
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl p-3 sm:p-4 flex flex-col sm:flex-row gap-3 shadow-sm dark:shadow-lg">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search audit trail by action, task ID, or details..."
            className="w-full min-h-[44px] bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-xs text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition"
          />
        </div>

        <select
          value={filterAction}
          onChange={(e) => setFilterAction(e.target.value)}
          className="min-h-[44px] bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl px-3 py-2 text-xs text-slate-800 dark:text-neutral-200 focus:outline-none focus:border-blue-500 transition cursor-pointer"
        >
          <option value="" className="bg-[#0c101a] text-white">All Action Types</option>
          <option value="ISSUE_SELECTED" className="bg-[#0c101a] text-white">ISSUE_SELECTED</option>
          <option value="WORKSPACE_PREPARED" className="bg-[#0c101a] text-white">WORKSPACE_PREPARED</option>
          <option value="ASSIGNMENT_COMMENT_POSTED" className="bg-[#0c101a] text-white">ASSIGNMENT_COMMENT_POSTED</option>
          <option value="VALIDATION_RUN" className="bg-[#0c101a] text-white">VALIDATION_RUN</option>
          <option value="PR_PUBLISHED" className="bg-[#0c101a] text-white">PR_PUBLISHED</option>
          <option value="TASK_CANCELLED" className="bg-[#0c101a] text-white">TASK_CANCELLED</option>
          <option value="DISCOVERY_SYNC" className="bg-[#0c101a] text-white">DISCOVERY_SYNC</option>
        </select>
      </div>

      {/* Logs Table / List */}
      <div className="bg-white dark:bg-[#0c101a] border border-slate-200 dark:border-white/10 rounded-2xl overflow-hidden shadow-sm dark:shadow-xl">
        {filteredLogs.length === 0 ? (
          <div className="p-12 text-center text-xs text-neutral-500">
            No audit records matching your search.
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-white/5">
            {filteredLogs.map(log => (
              <div key={log.id} className="p-4 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className={`text-[11px] font-mono px-2 py-0.5 rounded border ${getActionBadgeColor(log.action)}`}>
                      {log.action}
                    </span>
                    <span className="text-[11px] text-neutral-400">
                      Actor: <span className="font-semibold text-slate-900 dark:text-white">{log.actor}</span>
                    </span>
                  </div>

                  <span className="text-[11px] text-slate-500 dark:text-neutral-400 font-mono">
                    {new Date(log.created_at).toLocaleString()}
                  </span>
                </div>

                {log.details && (
                  <div className="bg-slate-50 dark:bg-[#05080f] border border-slate-200 dark:border-white/10 rounded-xl p-3 font-mono text-[11px] text-slate-800 dark:text-neutral-300 whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {JSON.stringify(log.details, null, 2)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <EnterpriseSSOModal
        isOpen={isSSOModalOpen}
        onClose={() => setIsSSOModalOpen(false)}
      />
    </div>
  );
};
