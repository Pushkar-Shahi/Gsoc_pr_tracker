import React, { useState } from 'react';
import { 
  ShieldCheck, ShieldAlert, Play, CheckCircle2, XCircle, 
  Terminal, FileCode, AlertTriangle, Send, ExternalLink, RefreshCw,
  Folder, GitBranch, Check, Layers, ChevronDown, MessageSquare, GitPullRequest
} from 'lucide-react';
import { Task, PlatformSettings } from '../types';
import { LiveConsoleModal } from './LiveConsoleModal';

interface ValidationViewProps {
  task: Task | null;
  tasks?: Task[];
  settings: PlatformSettings | null;
  onSelectTask?: (task: Task) => void;
  onRunValidation: (taskId: string, customCommand?: string) => Promise<any>;
  onOverrideValidation?: (taskId: string) => Promise<any>;
  onPublishPR: (taskId: string, forceOverride?: boolean) => Promise<any>;
}

export const ValidationView: React.FC<ValidationViewProps> = ({
  task,
  tasks = [],
  settings,
  onSelectTask,
  onRunValidation,
  onOverrideValidation,
  onPublishPR,
}) => {
  const [customTestCmd, setCustomTestCmd] = useState('');
  const [isValidating, setIsValidating] = useState(false);
  const [isStreamConsoleOpen, setIsStreamConsoleOpen] = useState(false);
  const [isOverriding, setIsOverriding] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [statusFeedback, setStatusFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Eligible tasks with active workspaces or pipeline status
  const selectableTasks = tasks.filter(t => !['CANCELLED', 'MERGED_OR_CLOSED'].includes(t.workflow_state));

  if (!task) {
    return (
      <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-10 text-center space-y-6 shadow-xl">
        <div className="w-12 h-12 rounded-2xl bg-purple-500/10 border border-purple-500/20 text-purple-400 flex items-center justify-center mx-auto shadow-md">
          <ShieldCheck className="w-6 h-6" />
        </div>
        <div className="space-y-1">
          <h3 className="text-base font-bold text-white">No Task Currently Selected for Validation</h3>
          <p className="text-xs text-neutral-400 max-w-md mx-auto">
            Choose an active task from below to run the automated test suite, inspect Git diff security, and publish your PR.
          </p>
        </div>

        {selectableTasks.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl mx-auto pt-2">
            {selectableTasks.map(t => (
              <button
                key={t.id}
                onClick={() => onSelectTask && onSelectTask(t)}
                className="bg-[#0c101a] hover:bg-white/5 border border-white/10 hover:border-purple-500/40 p-4 rounded-2xl text-left transition flex items-center justify-between group"
              >
                <div className="space-y-1 overflow-hidden">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] px-2 py-0.5 rounded-lg bg-white/5 border border-white/10 text-emerald-400">
                      {t.issue?.repository?.name} #{t.issue?.issue_number}
                    </span>
                    <span className="text-[10px] uppercase font-semibold text-neutral-400">
                      {t.workflow_state.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <h4 className="text-xs font-semibold text-white truncate">{t.issue?.title}</h4>
                </div>
                <span className="text-xs font-bold text-purple-400 group-hover:translate-x-1 transition-transform">
                  Validate &rarr;
                </span>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-500 italic">No tasks currently active in pipeline.</p>
        )}
      </div>
    );
  }

  const diffReport = task.diff_security_report;
  const testResults = task.validation_results;
  const isReadyToPublish = task.workflow_state === 'READY_TO_PUBLISH';
  const isValidationFailed = task.workflow_state === 'VALIDATION_FAILED';
  const isPrCreated = task.workflow_state === 'PR_CREATED';

  const handleRunValidation = async () => {
    setIsValidating(true);
    setStatusFeedback(null);
    try {
      const res = await onRunValidation(task.id, customTestCmd.trim() || undefined);
      if (res.passed) {
        setStatusFeedback({ type: 'success', message: res.message || 'All validation checks and tests passed cleanly!' });
      } else {
        setStatusFeedback({ type: 'error', message: res.message || 'Validation failed: Test suite returned a non-zero exit code or security issues were found.' });
      }
    } catch (err: any) {
      setStatusFeedback({ type: 'error', message: `Validation error: ${err.message}` });
    } finally {
      setIsValidating(false);
    }
  };

  const handleOverride = async () => {
    if (!onOverrideValidation) return;
    setIsOverriding(true);
    setStatusFeedback(null);
    try {
      await onOverrideValidation(task.id);
      setStatusFeedback({ type: 'success', message: 'Manual override applied: Task marked READY_TO_PUBLISH.' });
    } catch (err: any) {
      setStatusFeedback({ type: 'error', message: `Override error: ${err.message}` });
    } finally {
      setIsOverriding(false);
    }
  };

  const handlePublish = async (force: boolean = false) => {
    setIsPublishing(true);
    setStatusFeedback(null);
    try {
      const res = await onPublishPR(task.id, force);
      if (res.success) {
        setStatusFeedback({ type: 'success', message: res.message });
      } else {
        setStatusFeedback({ type: 'error', message: res.message || 'Publication was blocked.' });
      }
    } catch (err: any) {
      setStatusFeedback({ type: 'error', message: `Publication error: ${err.message}` });
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Validation Header */}
      <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/10">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-1.5">
              <span className="font-mono text-xs px-2.5 py-0.5 rounded-lg bg-white/5 border border-white/10 text-emerald-400 font-semibold">
                {task.issue?.repository?.full_name}
              </span>
              <span className="text-xs text-neutral-400 font-semibold">
                Issue #{task.issue?.issue_number}
              </span>
              <span className={`text-[10px] uppercase font-bold px-2.5 py-0.5 rounded-full border ${
                isReadyToPublish ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' :
                isValidationFailed ? 'bg-red-500/10 text-red-400 border-red-500/30' :
                'bg-purple-500/10 text-purple-400 border-purple-500/20'
              }`}>
                {task.workflow_state.replace(/_/g, ' ')}
              </span>

              {/* Task Switcher Dropdown */}
              {selectableTasks.length > 1 && onSelectTask && (
                <div className="relative inline-block ml-2">
                  <select
                    value={task.id}
                    onChange={(e) => {
                      const found = selectableTasks.find(t => t.id === e.target.value);
                      if (found) onSelectTask(found);
                    }}
                    className="bg-[#05080f] border border-white/10 text-[11px] text-neutral-300 rounded-lg px-2 py-1 pr-6 focus:outline-none focus:border-purple-500 cursor-pointer appearance-none"
                  >
                    {selectableTasks.map(t => (
                      <option key={t.id} value={t.id}>
                        Switch to #{t.issue?.issue_number} ({t.issue?.repository?.name})
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="w-3 h-3 text-neutral-400 absolute right-2 top-2 pointer-events-none" />
                </div>
              )}
            </div>

            <h2 className="text-lg font-bold text-white">{task.issue?.title}</h2>

            {/* Direct Links Bar */}
            <div className="flex flex-wrap items-center gap-2 pt-2 text-xs">
              {task.issue?.html_url && (
                <a
                  href={task.issue.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 hover:border-white/20 text-neutral-300 hover:text-white flex items-center gap-1 transition"
                  title="Open issue thread on GitHub"
                >
                  <span>Issue #{task.issue.issue_number}</span>
                  <ExternalLink className="w-3 h-3 text-neutral-400" />
                </a>
              )}

              {task.assignment_comment_id && (
                <a
                  href={task.assignment_comment_id.startsWith('http') ? task.assignment_comment_id : `${task.issue?.html_url}#issuecomment-${task.assignment_comment_id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="px-2.5 py-1 rounded-lg bg-cyan-950/40 border border-cyan-800/50 hover:bg-cyan-900/50 text-cyan-300 flex items-center gap-1.5 transition font-medium"
                  title="View assignment comment on GitHub"
                >
                  <MessageSquare className="w-3 h-3 text-cyan-400" />
                  <span>View Comment</span>
                  <ExternalLink className="w-3 h-3 text-cyan-400/80" />
                </a>
              )}

              {task.pr_url && (
                <a
                  href={task.pr_url}
                  target="_blank"
                  rel="noreferrer"
                  className="px-2.5 py-1 rounded-lg bg-purple-950/40 border border-purple-800/50 hover:bg-purple-900/50 text-purple-300 flex items-center gap-1.5 transition font-semibold"
                  title="Open pull request on GitHub"
                >
                  <GitPullRequest className="w-3 h-3 text-purple-400" />
                  <span>PR #{task.pr_number}</span>
                  <ExternalLink className="w-3 h-3 text-purple-400/80" />
                </a>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isValidationFailed && onOverrideValidation && (
              <button
                type="button"
                onClick={handleOverride}
                disabled={isOverriding}
                className="px-4 py-2.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-semibold transition flex items-center gap-1.5 active:scale-95 disabled:opacity-50"
                title="Override validation checks and proceed to publication gate"
              >
                <ShieldAlert className="w-4 h-4 text-amber-400" />
                <span>{isOverriding ? 'Applying...' : 'Override & Mark Ready'}</span>
              </button>
            )}

            <button
              onClick={() => setIsStreamConsoleOpen(true)}
              className="px-4 py-2.5 rounded-xl bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/30 text-xs font-semibold shadow-lg shadow-cyan-600/10 active:scale-95 transition flex items-center gap-1.5"
              title="Open real-time sandboxed terminal stream"
            >
              <Terminal className="w-3.5 h-3.5 text-cyan-400" />
              <span>Live Terminal</span>
            </button>

            <button
              onClick={handleRunValidation}
              disabled={isValidating}
              className="px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold text-xs shadow-lg shadow-purple-600/20 active:scale-95 transition flex items-center gap-2 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isValidating ? 'animate-spin' : ''}`} />
              <span>{isValidating ? 'Running Validation...' : 'Run Validation Suite'}</span>
            </button>
          </div>
        </div>

        {/* Status Notification Alert */}
        {statusFeedback && (
          <div className={`p-4 rounded-2xl border text-xs flex items-center justify-between gap-3 animate-fade-in ${
            statusFeedback.type === 'success' 
              ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300' 
              : 'bg-red-950/40 border-red-500/40 text-red-300'
          }`}>
            <div className="flex items-center gap-2.5">
              {statusFeedback.type === 'success' ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
              )}
              <span className="leading-relaxed font-medium">{statusFeedback.message}</span>
            </div>

            {statusFeedback.type === 'error' && onOverrideValidation && (
              <button
                type="button"
                onClick={handleOverride}
                className="px-3 py-1 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-white border border-red-500/40 text-[11px] font-semibold shrink-0"
              >
                Bypass & Allow PR
              </button>
            )}
          </div>
        )}

        {/* Custom Test Command Input */}
        <div className="bg-[#05080f] border border-white/10 rounded-xl p-4 space-y-2">
          <label className="block text-xs font-medium text-neutral-300">
            Custom Test Command (Optional — defaults to project detection e.g. <code className="text-purple-300">pytest</code>, <code className="text-purple-300">npm test</code>):
          </label>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={customTestCmd}
              onChange={(e) => setCustomTestCmd(e.target.value)}
              placeholder="e.g. pytest tests/test_feature.py or npm test"
              className="flex-1 bg-[#0c101a] border border-white/10 rounded-xl px-3.5 py-2 text-xs text-neutral-200 font-mono focus:outline-none focus:border-purple-500 transition"
            />
          </div>
        </div>
      </div>

      {/* Grid: Diff Security Scanner + Test Runner Output */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Diff Security Report */}
        <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              {diffReport?.passed !== false ? (
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
              ) : (
                <ShieldAlert className="w-4 h-4 text-red-400" />
              )}
              <h3 className="text-sm font-semibold text-white">Git Diff Security Scan</h3>
            </div>
            {diffReport && (
              <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${
                diffReport.passed ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-red-500/10 text-red-400 border-red-500/30'
              }`}>
                {diffReport.passed ? 'PASSED' : 'SECURITY ALERT'}
              </span>
            )}
          </div>

          {diffReport ? (
            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between text-neutral-400">
                <span>Changed Files:</span>
                <span className="font-mono text-white font-bold">{diffReport.changed_files_count ?? 0}</span>
              </div>

              {diffReport.secrets_detected?.length > 0 && (
                <div className="bg-red-950/30 border border-red-500/30 rounded-2xl p-3.5 text-red-300 space-y-1">
                  <div className="flex items-center gap-1.5 font-bold">
                    <AlertTriangle className="w-4 h-4 text-red-400" />
                    <span>Secrets Detected in Diff (Publication Blocked):</span>
                  </div>
                  {diffReport.secrets_detected.map((s, i) => (
                    <div key={i}>• {s}</div>
                  ))}
                </div>
              )}

              {diffReport.unrelated_files?.length > 0 && (
                <div className="bg-red-950/30 border border-red-500/30 rounded-2xl p-3.5 text-red-300 space-y-1">
                  <div className="font-bold">Prohibited or Environment Files Detected:</div>
                  {diffReport.unrelated_files.map((f, i) => (
                    <div key={i}>• {f}</div>
                  ))}
                </div>
              )}

              {/* Diff Preview */}
              <div>
                <span className="text-[11px] font-semibold text-neutral-400 block mb-1">Git Diff Preview:</span>
                <div className="bg-[#05080f] border border-white/10 rounded-xl p-3 font-mono text-[11px] text-neutral-300 max-h-60 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                  {diffReport.diff_preview || 'No diff detected yet.'}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-10 text-xs text-neutral-500">
              Run validation to scan worktree diff for credentials and unwanted files.
            </div>
          )}
        </div>

        {/* Right: Automated Test Execution Runner */}
        <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">Automated Test Execution</h3>
            </div>
            {testResults && (
              <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${
                testResults.passed ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-red-500/10 text-red-400 border-red-500/30'
              }`}>
                {testResults.passed ? 'TESTS PASSED' : 'TESTS FAILED'}
              </span>
            )}
          </div>

          {testResults && testResults.commands?.length > 0 ? (
            <div className="space-y-3">
              {testResults.commands.map((cmd, idx) => (
                <div key={idx} className="bg-[#05080f] border border-white/10 rounded-xl p-3.5 space-y-2">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="text-cyan-300 font-semibold">$ {cmd.command}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      cmd.exit_code === 0 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                    }`}>
                      exit code {cmd.exit_code}
                    </span>
                  </div>

                  {cmd.stdout && (
                    <div className="bg-[#0c101a] p-2.5 rounded-lg border border-white/10 font-mono text-[11px] text-neutral-300 max-h-40 overflow-y-auto whitespace-pre-wrap">
                      {cmd.stdout}
                    </div>
                  )}

                  {cmd.stderr && (
                    <div className="bg-red-950/20 p-2.5 rounded-lg border border-red-500/30 font-mono text-[11px] text-red-300 max-h-40 overflow-y-auto whitespace-pre-wrap">
                      {cmd.stderr}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-10 text-xs text-neutral-500">
              Run validation to execute the test suite and record command exit codes.
            </div>
          )}
        </div>
      </div>

      {/* Publication Gate Banner */}
      <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Pull Request Publication Gate</span>
            </h3>
            <p className="text-xs text-neutral-400 mt-1">
              Auto-Publish Setting is currently: <span className="font-bold text-white">{settings?.auto_publish_pr ? 'ENABLED (Automatic)' : 'DISABLED (Requires Manual Publish)'}</span>.
            </p>
          </div>

          <div className="flex items-center gap-3">
            {isPrCreated ? (
              <a
                href={task.pr_url}
                target="_blank"
                rel="noreferrer"
                className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-lg shadow-emerald-600/20 transition flex items-center gap-1.5"
              >
                <span>View Published PR #{task.pr_number}</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            ) : isValidationFailed ? (
              <div className="flex items-center gap-2">
                {onOverrideValidation && (
                  <button
                    onClick={handleOverride}
                    disabled={isOverriding}
                    className="px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-gray-950 font-bold text-xs shadow-md transition flex items-center gap-1.5 active:scale-95 disabled:opacity-50"
                  >
                    <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                    <span>Override & Mark Ready</span>
                  </button>
                )}

                <button
                  onClick={() => handlePublish(true)}
                  disabled={isPublishing}
                  className="px-4 py-2.5 rounded-xl bg-red-600/20 hover:bg-red-600/30 text-red-300 border border-red-500/40 font-semibold text-xs transition flex items-center gap-1.5 active:scale-95 disabled:opacity-50"
                  title="Force publish PR bypassing validation failures"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>{isPublishing ? 'Publishing...' : 'Force Publish PR'}</span>
                </button>
              </div>
            ) : (
              <button
                onClick={() => handlePublish(false)}
                disabled={!isReadyToPublish || isPublishing}
                className={`px-5 py-2.5 rounded-xl text-xs font-semibold shadow-lg transition flex items-center gap-2 ${
                  isReadyToPublish
                    ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/20 active:scale-95'
                    : 'bg-white/5 text-neutral-500 border border-white/10 cursor-not-allowed'
                }`}
              >
                <Send className="w-3.5 h-3.5" />
                <span>{isPublishing ? 'Publishing PR...' : 'Publish Pull Request'}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {task && (
        <LiveConsoleModal
          isOpen={isStreamConsoleOpen}
          onClose={() => setIsStreamConsoleOpen(false)}
          taskId={task.id}
          taskTitle={task.issue?.title}
          customCommand={customTestCmd}
          onFinished={(_passed) => {
            // Stream finished callback
          }}
        />
      )}
    </div>
  );
};
