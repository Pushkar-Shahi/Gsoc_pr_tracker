import React from 'react';
import { 
  GitBranch, Clock, AlertCircle, CheckCircle2, Terminal, 
  ShieldAlert, Send, ExternalLink, Trash2, ArrowRight,
  MessageSquare, GitPullRequest
} from 'lucide-react';
import { Task } from '../types';

interface TasksPipelineProps {
  tasks: Task[];
  onOpenWorkspace: (task: Task) => void;
  onOpenValidation: (task: Task) => void;
  onOpenAssignmentQueue: () => void;
  onCancelTask: (taskId: string) => void;
}

export const TasksPipeline: React.FC<TasksPipelineProps> = ({
  tasks,
  onOpenWorkspace,
  onOpenValidation,
  onOpenAssignmentQueue,
  onCancelTask,
}) => {
  const getStageColor = (state: string) => {
    switch (state) {
      case 'WORKSPACE_PREPARED':
      case 'COLLABORATIVE_WORK':
        return 'border-cyan-500/40 bg-cyan-950/20 text-cyan-400';
      case 'VALIDATING':
      case 'READY_FOR_VALIDATION':
        return 'border-purple-500/40 bg-purple-950/20 text-purple-400';
      case 'READY_TO_PUBLISH':
        return 'border-emerald-500/40 bg-emerald-950/20 text-emerald-400';
      case 'PR_CREATED':
      case 'IN_REVIEW':
        return 'border-blue-500/40 bg-blue-950/20 text-blue-400';
      case 'ASSIGNMENT_REQUEST_REQUIRED':
      case 'WAITING_FOR_MAINTAINER':
        return 'border-amber-500/40 bg-amber-950/20 text-amber-400';
      case 'VALIDATION_FAILED':
      case 'BLOCKED':
        return 'border-red-500/40 bg-red-950/20 text-red-400';
      default:
        return 'border-gray-700 bg-gray-900 text-gray-400';
    }
  };

  const getCommentUrl = (task: Task) => {
    if (task.assignment_comment_id) {
      if (task.assignment_comment_id.startsWith('http')) {
        return task.assignment_comment_id;
      }
      if (task.issue?.html_url) {
        return `${task.issue.html_url}#issuecomment-${task.assignment_comment_id}`;
      }
    }
    return task.workflow_state === 'WAITING_FOR_MAINTAINER' ? (task.issue?.html_url || '') : '';
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white">Active Tasks Pipeline</h2>
          <p className="text-xs text-gray-400">
            Track selected issues from preflight inspection through Antigravity collaborative coding to PR publication.
          </p>
        </div>
      </div>

      {tasks.length === 0 ? (
        <div className="bg-[#0c101a] border border-white/10 rounded-2xl p-12 text-center space-y-3 shadow-xl">
          <Terminal className="w-8 h-8 text-neutral-500 mx-auto" />
          <h3 className="text-base font-semibold text-white">No active tasks in progress</h3>
          <p className="text-xs text-neutral-400 max-w-sm mx-auto">
            Browse the Issue Inbox and select an open-source issue to initiate contribution preflight and workspace preparation.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {tasks.map((task) => {
            const commentUrl = getCommentUrl(task);

            return (
              <div
                key={task.id}
                className="bg-[#0c101a] border border-white/10 rounded-2xl p-5 shadow-xl space-y-4 hover:border-white/20 transition"
              >
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="space-y-1.5 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs px-2.5 py-0.5 rounded-lg bg-white/5 border border-white/10 text-emerald-400 font-semibold">
                        {task.issue?.repository?.full_name || 'Repository'}
                      </span>
                      <span className="text-xs text-neutral-400 font-mono">
                        #{task.issue?.issue_number}
                      </span>
                      <span className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border ${getStageColor(task.workflow_state)}`}>
                        {task.workflow_state.replace(/_/g, ' ')}
                      </span>
                    </div>

                    <h3 className="text-base font-semibold text-white">
                      {task.issue?.title}
                    </h3>

                    {/* Direct Links Bar */}
                    <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                      {task.issue?.html_url && (
                        <a
                          href={task.issue.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 hover:border-white/20 text-neutral-300 hover:text-white flex items-center gap-1 transition"
                          title="Open issue on GitHub"
                        >
                          <span>Issue #{task.issue.issue_number}</span>
                          <ExternalLink className="w-3 h-3 text-neutral-400" />
                        </a>
                      )}

                      {commentUrl && (
                        <a
                          href={commentUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg bg-cyan-950/50 border border-cyan-800/60 hover:bg-cyan-900/60 text-cyan-300 flex items-center gap-1.5 transition font-medium"
                          title="View posted assignment comment on GitHub"
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
                          className="px-2.5 py-1 rounded-lg bg-purple-950/50 border border-purple-800/60 hover:bg-purple-900/60 text-purple-300 flex items-center gap-1.5 transition font-semibold"
                          title="Open pull request on GitHub"
                        >
                          <GitPullRequest className="w-3 h-3 text-purple-400" />
                          <span>PR #{task.pr_number}</span>
                          <ExternalLink className="w-3 h-3 text-purple-400/80" />
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Quick Action Buttons */}
                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    {task.workflow_state.includes('ASSIGNMENT') && (
                      <button
                        onClick={onOpenAssignmentQueue}
                        className="px-3 py-1.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-xs font-semibold transition"
                      >
                        Review Assignment Request
                      </button>
                    )}

                    {(task.workflow_state === 'WORKSPACE_PREPARED' || task.workflow_state === 'COLLABORATIVE_WORK' || task.workflow_state === 'READY_TO_WORK') && (
                      <button
                        onClick={() => onOpenWorkspace(task)}
                        className="px-4 py-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow-md shadow-cyan-600/20 active:scale-95 transition flex items-center gap-1.5"
                      >
                        <Terminal className="w-3.5 h-3.5" />
                        <span>Antigravity Workspace</span>
                      </button>
                    )}

                    {(task.workflow_state === 'READY_FOR_VALIDATION' || task.workflow_state === 'VALIDATING' || task.workflow_state === 'VALIDATION_FAILED' || task.workflow_state === 'READY_TO_PUBLISH') && (
                      <button
                        onClick={() => onOpenValidation(task)}
                        className="px-4 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-md shadow-purple-600/20 active:scale-95 transition flex items-center gap-1.5"
                      >
                        <span>Validate & Diff</span>
                      </button>
                    )}

                    {task.pr_url && (
                      <a
                        href={task.pr_url}
                        target="_blank"
                        rel="noreferrer"
                        className="px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/20 transition flex items-center gap-1.5"
                      >
                        <span>View PR #{task.pr_number}</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}

                    <button
                      onClick={() => onCancelTask(task.id)}
                      className="p-1.5 rounded-lg text-neutral-500 hover:text-rose-400 hover:bg-rose-950/20 transition"
                      title="Cancel task and clean up workspace"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

              {/* Worktree & Branch Info */}
              {task.branch_name && (
                <div className="bg-[#05080f] border border-white/10 rounded-xl p-3 flex flex-wrap items-center justify-between text-xs text-neutral-400 gap-2">
                  <div className="flex items-center gap-2">
                    <GitBranch className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Working Branch:</span>
                    <span className="font-mono text-neutral-200 font-semibold">{task.branch_name}</span>
                  </div>
                  {task.worktree_path && (
                    <div className="truncate max-w-md font-mono text-[11px] text-neutral-400" title={task.worktree_path}>
                      {task.worktree_path}
                    </div>
                  )}
                </div>
              )}

              {/* Explainable Diagnostics Banner for Blocked or Unresolved Stages */}
              {task.blocked_reason && (
                <div className="bg-red-950/20 border border-red-500/30 rounded-xl p-3.5 text-xs text-red-300 flex items-start gap-2.5">
                  <ShieldAlert className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <div className="font-semibold text-red-200">
                      Diagnostics & Policy Guardrail Reason:
                    </div>
                    <p className="text-gray-300 leading-relaxed">
                      {task.blocked_reason}
                    </p>
                  </div>
                </div>
              )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
