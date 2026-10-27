import React, { useState } from 'react';
import { History, Search, Filter, ShieldCheck, Terminal, Clock, CheckCircle } from 'lucide-react';
import { AuditLog } from '../types';

interface ActivityHistoryViewProps {
  logs: AuditLog[];
}

export const ActivityHistoryView: React.FC<ActivityHistoryViewProps> = ({ logs }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterAction, setFilterAction] = useState('');

  const filteredLogs = logs.filter(log => {
    const matchesSearch = !searchTerm || 
      log.action.toLowerCase().includes(searchTerm.toLowerCase()) ||
      JSON.stringify(log.details).toLowerCase().includes(searchTerm.toLowerCase());
    const matchesAction = !filterAction || log.action === filterAction;
    return matchesSearch && matchesAction;
  });

  const getActionBadgeColor = (action: string) => {
    if (action.includes('PR_PUBLISHED')) return 'bg-white text-black border-white font-bold';
    if (action.includes('VALIDATION')) return 'bg-white/15 text-white border-white/30';
    if (action.includes('ASSIGNMENT')) return 'bg-neutral-800 text-white border-white/20';
    if (action.includes('WORKSPACE')) return 'bg-neutral-900 text-neutral-200 border-white/10';
    return 'bg-[#111111] text-neutral-300 border-white/10';
  };

  return (
    <div className="space-y-6 animate-fade-in-up">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-extrabold text-white">Immutable Activity Audit Trail</h2>
            <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-full bg-white/10 text-white border border-white/20">
              {logs.length} Events
            </span>
          </div>
          <p className="text-xs text-neutral-400 mt-1">
            Cryptographically stored timestamped record of every workflow transition, decision, and external GitHub interaction.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-[#080808] border border-white/10 rounded-2xl p-3 sm:p-4 flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-neutral-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search audit trail by action, task ID, or details..."
            className="w-full min-h-[44px] bg-[#000000] border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-white transition"
          />
        </div>

        <select
          value={filterAction}
          onChange={(e) => setFilterAction(e.target.value)}
          className="min-h-[44px] bg-[#000000] border border-white/10 rounded-xl px-3 py-2 text-xs text-neutral-200 focus:outline-none focus:border-white transition cursor-pointer"
        >
          <option value="" className="bg-[#000000] text-white">All Action Types</option>
          <option value="ISSUE_SELECTED" className="bg-[#000000] text-white">ISSUE_SELECTED</option>
          <option value="WORKSPACE_PREPARED" className="bg-[#000000] text-white">WORKSPACE_PREPARED</option>
          <option value="ASSIGNMENT_COMMENT_POSTED" className="bg-[#000000] text-white">ASSIGNMENT_COMMENT_POSTED</option>
          <option value="VALIDATION_RUN" className="bg-[#000000] text-white">VALIDATION_RUN</option>
          <option value="PR_PUBLISHED" className="bg-[#000000] text-white">PR_PUBLISHED</option>
          <option value="TASK_CANCELLED" className="bg-[#000000] text-white">TASK_CANCELLED</option>
          <option value="DISCOVERY_SYNC" className="bg-[#000000] text-white">DISCOVERY_SYNC</option>
        </select>
      </div>

      {/* Logs Table / List */}
      <div className="bg-[#080808] border border-white/10 rounded-2xl overflow-hidden shadow-xl">
        {filteredLogs.length === 0 ? (
          <div className="p-12 text-center text-xs text-neutral-500">
            No audit records matching your search.
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {filteredLogs.map(log => (
              <div key={log.id} className="p-4 hover:bg-[#0f0f0f] transition space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className={`text-[11px] font-mono px-2 py-0.5 rounded border ${getActionBadgeColor(log.action)}`}>
                      {log.action}
                    </span>
                    <span className="text-[11px] text-neutral-400">
                      Actor: <span className="font-semibold text-white">{log.actor}</span>
                    </span>
                  </div>

                  <span className="text-[11px] text-neutral-400 font-mono">
                    {new Date(log.created_at).toLocaleString()}
                  </span>
                </div>

                {log.details && (
                  <div className="bg-[#000000] border border-white/10 rounded-xl p-3 font-mono text-[11px] text-neutral-300 whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {JSON.stringify(log.details, null, 2)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
