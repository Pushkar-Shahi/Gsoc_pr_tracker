import React, { useState } from 'react';
import { 
  FileText, CheckCircle2, RefreshCw, Send, AlertTriangle, 
  ExternalLink, Clock, MessageSquare, ShieldCheck, ArrowRight,
  GitPullRequest
} from 'lucide-react';
import { Task } from '../types';

interface AssignmentQueueProps {
  tasks: Task[];
  onApproveComment: (taskId: string, commentText: string) => Promise<void>;
  onRecheckAssignment: (taskId: string) => Promise<void>;
  onProceedToWorkspace: (task: Task) => void;
}

export const AssignmentQueue: React.FC<AssignmentQueueProps> = ({
  tasks,
  onApproveComment,
  onRecheckAssignment,
  onProceedToWorkspace,
}) => {
  const [commentDrafts, setCommentDrafts] = useState<Record<string, string>>({});
  const [loadingTaskId, setLoadingTaskId] = useState<string | null>(null);

  const pendingApprovalTasks = tasks.filter(t => t.workflow_state === 'ASSIGNMENT_REQUEST_REQUIRED');
  const waitingMaintainerTasks = tasks.filter(t => t.workflow_state === 'WAITING_FOR_MAINTAINER');
  const readyTasks = tasks.filter(t => t.workflow_state === 'READY_TO_WORK' && t.assignment_required);

  const getCommentUrl = (task: Task) => {
    if (task.assignment_comment_id) {
      if (task.assignment_comment_id.startsWith('http')) {
        return task.assignment_comment_id;
      }
      if (task.issue?.html_url) {
        return `${task.issue.html_url}#issuecomment-${task.assignment_comment_id}`;
      }
    }
    return task.issue?.html_url || '';
  };

  const handleCommentChange = (taskId: string, text: string) => {
    setCommentDrafts(prev => ({ ...prev, [taskId]: text }));
  };

  const handleApprove = async (taskId: string, defaultComment: string) => {
    const textToSubmit = commentDrafts[taskId] !== undefined ? commentDrafts[taskId] : defaultComment;
    setLoadingTaskId(taskId);
    try {
      await onApproveComment(taskId, textToSubmit);
    } finally {
      setLoadingTaskId(null);
    }
  };

  const handleRecheck = async (taskId: string) => {
    setLoadingTaskId(taskId);
    try {
      await onRecheckAssignment(taskId);
    } finally {
      setLoadingTaskId(null);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h2 className="text-lg font-bold text-white">Maintainer Assignment Queue</h2>
        <p className="text-xs text-gray-400">
          Enforces repository-specific assignment prerequisites. No comment is ever posted without your explicit review and authorization.
        </p>
      </div>

      {/* Section 1: Drafts Awaiting Your Explicit Approval */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-amber-400">
          <AlertTriangle className="w-4 h-4" />
          <span>Draft Requests Awaiting Your Explicit Approval ({pendingApprovalTasks.length})</span>
        </div>

        {pendingApprovalTasks.length === 0 ? (
          <div className="bg-[#111827] border border-gray-800 rounded-2xl p-6 text-center text-xs text-gray-500">
            No assignment requests currently awaiting approval.
          </div>
        ) : (
          <div className="space-y-4">
            {pendingApprovalTasks.map(task => {
              const defaultComment = task.draft_assignment_comment || '';
              const currentText = commentDrafts[task.id] !== undefined ? commentDrafts[task.id] : defaultComment;

              return (
                <div key={task.id} className="bg-[#111827] border border-amber-500/30 rounded-2xl p-5 shadow-xl space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-gray-800">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs px-2.5 py-0.5 rounded bg-gray-900 border border-gray-700 text-emerald-300">
                          {task.issue?.repository?.full_name}
                        </span>
                        <span className="text-xs text-gray-400 font-semibold">
                          #{task.issue?.issue_number}
                        </span>
                      </div>
                      <h4 className="text-sm font-semibold text-white mt-1">{task.issue?.title}</h4>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {task.issue?.html_url && (
                        <a
                          href={task.issue.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-xs text-gray-300 hover:text-white flex items-center gap-1 transition"
                        >
                          <span>View Issue</span>
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                      {task.pr_url && (
                        <a
                          href={task.pr_url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-3 py-1.5 rounded-lg bg-purple-500/10 hover:bg-purple-500/20 text-xs text-purple-300 border border-purple-500/30 flex items-center gap-1 transition"
                        >
                          <GitPullRequest className="w-3.5 h-3.5" />
                          <span>View PR #{task.pr_number}</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Rule Evidence Alert */}
                  <div className="bg-amber-950/20 border border-amber-500/20 rounded-xl p-3 text-xs text-amber-300">
                    <span className="font-semibold">Repository Rule Evidence:</span> The maintainer or contributing guidelines specify that contributors must be explicitly assigned prior to submitting code.
                  </div>

                  {/* Draft Comment Editor */}
                  <div className="space-y-2">
                    <label className="block text-xs font-medium text-gray-300">
                      Proposed GitHub Assignment Request Comment (You can edit before posting):
                    </label>
                    <textarea
                      rows={3}
                      value={currentText}
                      onChange={(e) => handleCommentChange(task.id, e.target.value)}
                      className="w-full bg-[#0b0f19] border border-gray-700 rounded-xl p-3 text-xs text-gray-200 font-sans focus:outline-none focus:border-amber-500"
                    />
                  </div>

                  {/* Explicit Approval Action */}
                  <div className="flex items-center justify-between pt-2">
                    <p className="text-[11px] text-gray-500">
                      Clicking approve will submit this exact comment to the GitHub issue using your configured token.
                    </p>

                    <button
                      onClick={() => handleApprove(task.id, defaultComment)}
                      disabled={loadingTaskId === task.id}
                      className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-gray-950 font-bold text-xs shadow-lg shadow-amber-600/20 active:scale-95 transition flex items-center gap-2"
                    >
                      <Send className="w-3.5 h-3.5" />
                      <span>{loadingTaskId === task.id ? 'Posting...' : 'Approve & Post Comment'}</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Section 2: Requests Waiting for Maintainer Confirmation */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-cyan-400">
          <Clock className="w-4 h-4" />
          <span>Waiting for Maintainer Assignment Confirmation ({waitingMaintainerTasks.length})</span>
        </div>

        {waitingMaintainerTasks.length === 0 ? (
          <div className="bg-[#111827] border border-gray-800 rounded-2xl p-6 text-center text-xs text-gray-500">
            No requests currently waiting for maintainer confirmation.
          </div>
        ) : (
          <div className="space-y-4">
            {waitingMaintainerTasks.map(task => {
              const commentUrl = getCommentUrl(task);
              const hasSpecificComment = Boolean(task.assignment_comment_id);

              return (
                <div key={task.id} className="bg-[#111827] border border-cyan-500/30 rounded-2xl p-5 shadow-xl space-y-4 hover:border-cyan-500/50 transition">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                    <div className="space-y-1.5 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs px-2.5 py-0.5 rounded bg-gray-900 border border-gray-700 text-emerald-300 font-semibold">
                          {task.issue?.repository?.full_name}
                        </span>
                        <span className="text-xs text-cyan-400 font-semibold px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20">
                          Waiting for assignment response
                        </span>
                        {task.issue?.issue_number && (
                          <span className="text-xs text-gray-400 font-mono">
                            #{task.issue.issue_number}
                          </span>
                        )}
                      </div>

                      <h4 className="text-base font-semibold text-white mt-1">{task.issue?.title}</h4>
                      
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-400 pt-0.5">
                        <p>
                          Assignment comment posted: <span className="text-gray-200">{task.assignment_posted_at ? new Date(task.assignment_posted_at).toLocaleString() : 'Recently'}</span>
                        </p>
                        {task.assignment_comment_id && (
                          <span className="font-mono text-[11px] text-gray-500">
                            Comment ID: #{task.assignment_comment_id}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Direct Links and Action Buttons */}
                    <div className="flex flex-wrap sm:flex-col items-start sm:items-end gap-2 shrink-0">
                      <div className="flex flex-wrap items-center gap-2">
                        {/* Direct Link to Comment on GitHub */}
                        {commentUrl && (
                          <a
                            href={commentUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="px-3 py-1.5 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-semibold text-xs transition flex items-center gap-1.5 shadow-sm active:scale-95"
                            title="Open comment on GitHub in a new tab"
                          >
                            <MessageSquare className="w-3.5 h-3.5 text-cyan-400" />
                            <span>{hasSpecificComment ? 'View Comment on GitHub' : 'View on GitHub'}</span>
                            <ExternalLink className="w-3 h-3 text-cyan-400/80" />
                          </a>
                        )}

                        {/* Direct Link to Issue */}
                        {task.issue?.html_url && (
                          <a
                            href={task.issue.html_url}
                            target="_blank"
                            rel="noreferrer"
                            className="px-3 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white border border-gray-700 text-xs font-medium transition flex items-center gap-1.5"
                            title="Open issue thread on GitHub"
                          >
                            <span>Issue #{task.issue.issue_number}</span>
                            <ExternalLink className="w-3 h-3 text-gray-400" />
                          </a>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        {/* Direct Link to PR (if created) */}
                        {task.pr_url && (
                          <a
                            href={task.pr_url}
                            target="_blank"
                            rel="noreferrer"
                            className="px-3 py-1.5 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold text-xs transition flex items-center gap-1.5 shadow-sm active:scale-95"
                          >
                            <GitPullRequest className="w-3.5 h-3.5 text-purple-400" />
                            <span>View PR #{task.pr_number}</span>
                            <ExternalLink className="w-3 h-3 text-purple-400/80" />
                          </a>
                        )}

                        <button
                          onClick={() => handleRecheck(task.id)}
                          disabled={loadingTaskId === task.id}
                          className="px-4 py-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs shadow-md shadow-cyan-600/20 active:scale-95 transition flex items-center gap-2"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${loadingTaskId === task.id ? 'animate-spin' : ''}`} />
                          <span>Recheck Status on GitHub</span>
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Submitted Comment Quote Block */}
                  {task.draft_assignment_comment && (
                    <div className="bg-[#0b0f19] border border-gray-800/80 rounded-xl p-3.5 space-y-2">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-semibold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
                          <MessageSquare className="w-3.5 h-3.5" />
                          <span>Submitted Assignment Request Comment</span>
                        </span>
                        {commentUrl && (
                          <a
                            href={commentUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 text-[11px] font-medium transition"
                          >
                            <span>Open Direct Comment on GitHub</span>
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        )}
                      </div>
                      <p className="text-xs text-gray-200 font-mono whitespace-pre-wrap leading-relaxed bg-gray-900/60 p-3 rounded-lg border border-gray-800">
                        {task.draft_assignment_comment}
                      </p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Section 3: Verified & Ready for Workspace */}
      {readyTasks.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
            <CheckCircle2 className="w-4 h-4" />
            <span>Assignment Verified — Ready to Prepare Workspace ({readyTasks.length})</span>
          </div>

          <div className="space-y-3">
            {readyTasks.map(task => {
              const commentUrl = getCommentUrl(task);

              return (
                <div key={task.id} className="bg-[#111827] border border-emerald-500/30 rounded-2xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs px-2.5 py-0.5 rounded bg-gray-900 border border-gray-700 text-emerald-300">
                        {task.issue?.repository?.full_name}
                      </span>
                      {task.issue?.issue_number && (
                        <span className="text-xs text-gray-400">
                          #{task.issue.issue_number}
                        </span>
                      )}
                    </div>
                    <h4 className="text-sm font-semibold text-white mt-1">{task.issue?.title}</h4>
                    <p className="text-xs text-emerald-400/90 mt-0.5">
                      Maintainer prerequisite confirmed. Ready for collaborative work in Antigravity.
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    {commentUrl && (
                      <a
                        href={commentUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="px-3 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white border border-gray-700 text-xs font-medium transition flex items-center gap-1.5"
                      >
                        <MessageSquare className="w-3.5 h-3.5 text-cyan-400" />
                        <span>Comment</span>
                        <ExternalLink className="w-3 h-3 text-gray-400" />
                      </a>
                    )}
                    {task.issue?.html_url && (
                      <a
                        href={task.issue.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="px-3 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white border border-gray-700 text-xs font-medium transition flex items-center gap-1.5"
                      >
                        <span>Issue</span>
                        <ExternalLink className="w-3 h-3 text-gray-400" />
                      </a>
                    )}
                    {task.pr_url && (
                      <a
                        href={task.pr_url}
                        target="_blank"
                        rel="noreferrer"
                        className="px-3 py-1.5 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/30 text-xs font-semibold transition flex items-center gap-1.5"
                      >
                        <GitPullRequest className="w-3.5 h-3.5" />
                        <span>PR #{task.pr_number}</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}

                    <button
                      onClick={() => onProceedToWorkspace(task)}
                      className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-lg shadow-emerald-600/20 active:scale-95 transition flex items-center gap-1.5"
                    >
                      <span>Prepare Workspace</span>
                      <ArrowRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
