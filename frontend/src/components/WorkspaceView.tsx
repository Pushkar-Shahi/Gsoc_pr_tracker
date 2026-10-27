import React, { useState } from 'react';
import { 
  Terminal, Copy, Check, GitBranch, ExternalLink, Play, 
  CheckCircle2, Folder, ArrowRight, Trash2, AlertCircle, Info, RefreshCw, Cpu,
  MessageSquare, GitPullRequest
} from 'lucide-react';
import { Task } from '../types';

interface WorkspaceViewProps {
  task: Task | null;
  onPrepareWorkspace?: (taskId: string) => Promise<Task>;
  onOpenInAntigravity: (taskId: string) => Promise<{ success: boolean; message: string; fallback_prompt?: string }>;
  onMarkReadyForValidation: (taskId: string) => Promise<void>;
  onCancelTask: (taskId: string) => Promise<void>;
  onOpenBriefing?: () => void;
}

export const WorkspaceView: React.FC<WorkspaceViewProps> = ({
  task,
  onPrepareWorkspace,
  onOpenInAntigravity,
  onMarkReadyForValidation,
  onCancelTask,
  onOpenBriefing,
}) => {
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [copiedPath, setCopiedPath] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [launchMessage, setLaunchMessage] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false);

  if (!task) {
    return (
      <div className="bg-[#111827] border border-gray-800 rounded-2xl p-12 text-center space-y-3">
        <Terminal className="w-8 h-8 text-gray-500 mx-auto" />
        <h3 className="text-base font-semibold text-white">No active workspace selected</h3>
        <p className="text-xs text-gray-400 max-w-sm mx-auto">
          Select an issue from the Inbox or Tasks Pipeline to open its isolated Antigravity workspace.
        </p>
      </div>
    );
  }

  const commentUrl = task.assignment_comment_id
    ? (task.assignment_comment_id.startsWith('http')
        ? task.assignment_comment_id
        : (task.issue?.html_url ? `${task.issue.html_url}#issuecomment-${task.assignment_comment_id}` : ''))
    : (task.workflow_state === 'WAITING_FOR_MAINTAINER' ? (task.issue?.html_url || '') : '');

  const promptText = task.implementation_brief?.prompt_text || (
    `I am working on GitHub issue #${task.issue?.issue_number} for ${task.issue?.repository?.full_name}: '${task.issue?.title}'.\n\n` +
    `Issue details:\n${task.issue?.body || ''}\n\n` +
    `Please help me inspect the codebase, plan the minimal surgical changes, implement the fix, and verify tests pass.`
  );

  const manualOpenCommand = task.worktree_path 
    ? `open -a Antigravity "${task.worktree_path}"` 
    : '';

  const handleCopyPrompt = () => {
    navigator.clipboard.writeText(promptText);
    setCopiedPrompt(true);
    setTimeout(() => setCopiedPrompt(false), 2000);
  };

  const handleCopyPath = () => {
    if (task.worktree_path) {
      navigator.clipboard.writeText(task.worktree_path);
      setCopiedPath(true);
      setTimeout(() => setCopiedPath(false), 2000);
    }
  };

  const handleCopyCmd = () => {
    if (manualOpenCommand) {
      navigator.clipboard.writeText(manualOpenCommand);
      setCopiedCmd(true);
      setTimeout(() => setCopiedCmd(false), 2000);
    }
  };

  const handlePrepareOnly = async () => {
    if (!onPrepareWorkspace) return;
    setLaunching(true);
    setLaunchMessage('Preparing isolated Git worktree & branch from repository...');
    try {
      await onPrepareWorkspace(task.id);
      setLaunchMessage('Workspace prepared successfully! Ready to launch in Antigravity.');
    } catch (err: any) {
      setLaunchMessage(`Preparation error: ${err.message}`);
    } finally {
      setLaunching(false);
    }
  };

  const handleLaunchAntigravity = async () => {
    setLaunching(true);
    setLaunchMessage('Initiating Antigravity desktop handoff...');
    try {
      // If workspace is not yet prepared, prepare it first
      if (!task.worktree_path && onPrepareWorkspace) {
        setLaunchMessage('Preparing Git worktree and branch first...');
        await onPrepareWorkspace(task.id);
      }
      const res = await onOpenInAntigravity(task.id);
      setLaunchMessage(res.message || 'Antigravity desktop application launched successfully!');
    } catch (err: any) {
      setLaunchMessage(`Launch notice: ${err.message || 'Handoff command could not be invoked. Use the copyable command or prompt below.'}`);
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Workspace Header */}
      <div className="bg-[#111827] border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-gray-800">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-xs px-2.5 py-0.5 rounded bg-gray-900 border border-gray-700 text-emerald-300">
                {task.issue?.repository?.full_name}
              </span>
              <span className="text-xs text-gray-400">
                Issue #{task.issue?.issue_number}
              </span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                {task.workflow_state.replace(/_/g, ' ')}
              </span>
            </div>
            <h2 className="text-lg font-bold text-white">{task.issue?.title}</h2>

            {/* Direct Links Bar */}
            <div className="flex flex-wrap items-center gap-2 pt-2 text-xs">
              {task.issue?.html_url && (
                <a
                  href={task.issue.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="px-2.5 py-1 rounded-lg bg-gray-900 border border-gray-800 hover:border-gray-700 text-gray-300 hover:text-white flex items-center gap-1 transition"
                  title="Open issue thread on GitHub"
                >
                  <span>Issue #{task.issue.issue_number}</span>
                  <ExternalLink className="w-3 h-3 text-gray-400" />
                </a>
              )}

              {commentUrl && (
                <a
                  href={commentUrl}
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

          {/* Antigravity Desktop Launch Action */}
          <div className="flex flex-wrap items-center gap-2">
            {onOpenBriefing && (
              <button
                type="button"
                onClick={onOpenBriefing}
                className="px-4 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-emerald-300 hover:text-emerald-200 font-semibold text-xs border border-emerald-500/30 active:scale-95 transition flex items-center gap-1.5 shadow-sm"
              >
                <Cpu className="w-3.5 h-3.5 text-emerald-400" />
                <span>View Autonomous Plan</span>
              </button>
            )}

            {!task.worktree_path && onPrepareWorkspace && (
              <button
                onClick={handlePrepareOnly}
                disabled={launching}
                className="px-4 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-200 font-semibold text-xs border border-gray-700 active:scale-95 transition flex items-center gap-1.5"
              >
                <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${launching ? 'animate-spin' : ''}`} />
                <span>Prepare Git Worktree</span>
              </button>
            )}

            <button
              onClick={handleLaunchAntigravity}
              disabled={launching}
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-emerald-600 hover:from-cyan-500 hover:to-emerald-500 text-white font-semibold text-xs shadow-lg shadow-cyan-600/20 active:scale-95 transition flex items-center gap-2"
            >
              <Terminal className="w-4 h-4" />
              <span>
                {launching 
                  ? 'Launching Antigravity...' 
                  : task.worktree_path 
                    ? 'Open in Antigravity App' 
                    : 'Prepare & Open in Antigravity'
                }
              </span>
            </button>
          </div>
        </div>

        {/* Launch Result Notification */}
        {launchMessage && (
          <div className="bg-cyan-950/30 border border-cyan-500/30 rounded-xl p-3.5 text-xs text-cyan-300 flex items-center gap-2.5 animate-fade-in shadow-inner">
            <Info className="w-4 h-4 text-cyan-400 shrink-0" />
            <span className="leading-relaxed">{launchMessage}</span>
          </div>
        )}

        {/* Worktree Path & Git Branch Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Worktree Directory Card */}
          <div className="bg-[#0b0f19] border border-gray-800 rounded-xl p-4 space-y-2">
            <div className="flex items-center justify-between text-xs text-gray-400">
              <span className="flex items-center gap-1.5 font-medium text-gray-300">
                <Folder className="w-3.5 h-3.5 text-cyan-400" />
                <span>Isolated Git Worktree Path</span>
              </span>
              {task.worktree_path && (
                <button
                  onClick={handleCopyPath}
                  className="flex items-center gap-1 text-emerald-400 hover:text-emerald-300 transition"
                >
                  {copiedPath ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedPath ? 'Copied' : 'Copy'}</span>
                </button>
              )}
            </div>
            <p className="font-mono text-xs text-gray-200 bg-gray-900/80 p-2.5 rounded-lg border border-gray-800 truncate" title={task.worktree_path || undefined}>
              {task.worktree_path || 'Pending preparation (click "Prepare & Open in Antigravity" above)'}
            </p>
          </div>

          {/* Task Branch Card */}
          <div className="bg-[#0b0f19] border border-gray-800 rounded-xl p-4 space-y-2">
            <div className="flex items-center justify-between text-xs text-gray-400">
              <span className="flex items-center gap-1.5 font-medium text-gray-300">
                <GitBranch className="w-3.5 h-3.5 text-emerald-400" />
                <span>Dedicated Task Branch</span>
              </span>
              <span className="text-[11px] text-gray-500">
                Based on: {task.issue?.repository?.default_branch || 'main'}
              </span>
            </div>
            <p className="font-mono text-xs text-emerald-300 bg-gray-900/80 p-2.5 rounded-lg border border-gray-800 truncate">
              {task.branch_name || 'Will be generated: fix/issue-<number>-<slug>'}
            </p>
          </div>
        </div>

        {/* Quick Terminal Command Fallback */}
        {manualOpenCommand && (
          <div className="bg-[#0b0f19] border border-gray-800/80 rounded-xl p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2 text-gray-400">
              <Terminal className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              <span>Direct Shell / Terminal Command:</span>
              <code className="text-gray-200 font-mono bg-gray-900 px-2 py-0.5 rounded border border-gray-800">{manualOpenCommand}</code>
            </div>
            <button
              onClick={handleCopyCmd}
              className="px-2.5 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-[11px] font-semibold border border-gray-700 transition flex items-center gap-1 self-start sm:self-auto"
            >
              {copiedCmd ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              <span>{copiedCmd ? 'Copied' : 'Copy Command'}</span>
            </button>
          </div>
        )}
      </div>

      {/* Copyable Implementation Prompt for Antigravity */}
      <div className="bg-[#111827] border border-gray-800 rounded-2xl p-6 shadow-xl space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Terminal className="w-4 h-4 text-emerald-400" />
              <span>Ready-to-Paste Antigravity Implementation Prompt</span>
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Copy and paste this structured prompt into your Google Antigravity chat to begin collaborative implementation.
            </p>
          </div>

          <button
            onClick={handleCopyPrompt}
            className="px-3.5 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-semibold border border-gray-700 transition flex items-center gap-1.5 active:scale-95"
          >
            {copiedPrompt ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copiedPrompt ? 'Copied to Clipboard!' : 'Copy Prompt'}</span>
          </button>
        </div>

        <div className="bg-[#0b0f19] border border-gray-800 rounded-xl p-4 font-mono text-xs text-gray-300 whitespace-pre-wrap max-h-56 overflow-y-auto leading-relaxed">
          {promptText}
        </div>
      </div>

      {/* Collaboration Rules & Checklist */}
      <div className="bg-[#111827] border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
        <h3 className="text-sm font-semibold text-white">Collaborative Workflow Checklist</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-gray-300">
          <div className="bg-[#0b0f19] p-3 rounded-xl border border-gray-800 flex items-start gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span>Isolated worktree prevents conflicts with existing projects or repositories.</span>
          </div>
          <div className="bg-[#0b0f19] p-3 rounded-xl border border-gray-800 flex items-start gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span>Implementation brief generated at <code>.antigravity/BRIEF.md</code>.</span>
          </div>
          <div className="bg-[#0b0f19] p-3 rounded-xl border border-gray-800 flex items-start gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span>Preserve repository formatting and existing docstrings without unrelated edits.</span>
          </div>
          <div className="bg-[#0b0f19] p-3 rounded-xl border border-gray-800 flex items-start gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span>Diff will be automatically scanned for credentials before PR publication.</span>
          </div>
        </div>

        {/* Footer Completion Actions */}
        <div className="pt-4 border-t border-gray-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <button
            onClick={() => onCancelTask(task.id)}
            className="text-xs text-gray-500 hover:text-red-400 transition flex items-center gap-1.5"
          >
            <Trash2 className="w-4 h-4" />
            <span>Cancel Task & Delete Worktree</span>
          </button>

          <button
            onClick={() => onMarkReadyForValidation(task.id)}
            className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-lg shadow-emerald-600/20 active:scale-95 transition flex items-center gap-2 justify-center"
          >
            <span>Collaborative Work Complete &rarr; Proceed to Validation</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
