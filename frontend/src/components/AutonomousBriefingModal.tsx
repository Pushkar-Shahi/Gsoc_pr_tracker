import React, { useState } from 'react';
import { 
  X, Check, AlertTriangle, ArrowRight, ExternalLink, ShieldCheck, 
  Terminal, Sparkles, FileCode, CheckCircle2, Send, Cpu, 
  HelpCircle, RefreshCw, Layers, Shield, Zap
} from 'lucide-react';
import { Task } from '../types';

interface AutonomousBriefingModalProps {
  task: Task | null;
  isOpen: boolean;
  onClose: () => void;
  onApprove: (taskId: string, customComment?: string) => Promise<void>;
  onRegenerateBriefing?: (taskId: string) => Promise<void>;
}

export const AutonomousBriefingModal: React.FC<AutonomousBriefingModalProps> = ({
  task,
  isOpen,
  onClose,
  onApprove,
  onRegenerateBriefing,
}) => {
  if (!isOpen || !task) return null;

  return (
    <AutonomousBriefingModalContent
      key={task.id}
      task={task}
      onClose={onClose}
      onApprove={onApprove}
      onRegenerateBriefing={onRegenerateBriefing}
    />
  );
};

interface AutonomousBriefingModalContentProps {
  task: Task;
  onClose: () => void;
  onApprove: (taskId: string, customComment?: string) => Promise<void>;
  onRegenerateBriefing?: (taskId: string) => Promise<void>;
}

const AutonomousBriefingModalContent: React.FC<AutonomousBriefingModalContentProps> = ({
  task,
  onClose,
  onApprove,
  onRegenerateBriefing,
}) => {
  const brief = task.implementation_brief;
  const isAssignmentRequired = task.assignment_required || brief?.rule_check?.assignment_required;
  const initialComment = task.draft_assignment_comment || brief?.rule_check?.draft_comment || '';

  const [commentText, setCommentText] = useState(initialComment);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleApproveClick = async () => {
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await onApprove(task.id, isAssignmentRequired ? commentText : undefined);
      onClose();
    } catch (err: any) {
      setSubmitError(err.message || 'Execution error during approval.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegenerate = async () => {
    if (!onRegenerateBriefing) return;
    setIsRefreshing(true);
    try {
      await onRegenerateBriefing(task.id);
    } catch (err: any) {
      setSubmitError(err.message || 'Failed to refresh intelligence analysis.');
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="bg-[#0c101a] border border-white/10 rounded-2xl w-full max-w-4xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="px-6 py-5 border-b border-white/10 bg-[#080c14] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-emerald-500/20 to-cyan-500/20 border border-emerald-500/30 flex items-center justify-center shadow-lg">
              <Cpu className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs px-2.5 py-0.5 rounded-lg bg-white/5 border border-white/10 text-emerald-400 font-semibold">
                  {task.issue?.repository?.full_name}
                </span>
                <span className="text-xs text-neutral-400 font-medium">Issue #{task.issue?.issue_number}</span>
                <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                  Autonomous Plan
                </span>
                {brief?.ai_mode === 'live_byok' ? (
                  <span className="text-[10px] uppercase font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                    BYOK AI ({brief.ai_provider || 'LLM'} • {brief.ai_key_source || 'key'})
                  </span>
                ) : (
                  <span className="text-[10px] uppercase font-mono font-bold px-2 py-0.5 rounded-full bg-white/5 text-neutral-400 border border-white/10">
                    Heuristic Brief
                  </span>
                )}
              </div>
              <h3 className="text-base font-bold text-white mt-1 line-clamp-1">
                {task.issue?.title}
              </h3>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {task.issue?.html_url && (
              <a
                href={task.issue.html_url}
                target="_blank"
                rel="noreferrer"
                className="px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-neutral-300 hover:text-white border border-white/10 text-xs font-medium transition flex items-center gap-1.5 shadow-sm"
                title="Open original issue on GitHub"
              >
                <span>View on GitHub</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}

            {onRegenerateBriefing && (
              <button
                type="button"
                onClick={handleRegenerate}
                disabled={isRefreshing}
                className="p-2 rounded-xl text-neutral-400 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition"
                title="Refresh automated intelligence analysis"
              >
                <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-emerald-400' : ''}`} />
              </button>
            )}

            <button
              onClick={onClose}
              className="p-2 rounded-xl text-neutral-400 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Content: Tells the user everything about the issue */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 text-sm">
          
          {submitError && (
            <div className="p-4 rounded-2xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
              <span>{submitError}</span>
            </div>
          )}

          {/* Section 1: Executive Overview & Root Cause */}
          <div className="bg-[#05080f] border border-white/10 rounded-2xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-white font-semibold text-xs tracking-wider uppercase">
                <Sparkles className="w-4 h-4 text-emerald-400" />
                <span>Executive Problem Analysis</span>
              </div>
              {brief?.category && (
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 capitalize">
                  {brief.category}
                </span>
              )}
            </div>

            <p className="text-neutral-300 text-xs leading-relaxed">
              {brief?.executive_summary || task.issue?.ai_summary || task.issue?.body?.slice(0, 300) || 'Comprehensive issue analysis generated.'}
            </p>

            {brief?.root_cause_analysis && (
              <div className="pt-2 border-t border-white/10">
                <span className="text-[11px] font-semibold text-neutral-400 uppercase tracking-wider block mb-1">
                  Root Cause Hypothesis
                </span>
                <p className="text-xs text-neutral-300 leading-relaxed bg-[#0c101a] p-3 rounded-xl border border-white/10">
                  {brief.root_cause_analysis}
                </p>
              </div>
            )}
          </div>

          {/* Section 2: Affected Codebase Files & Modules */}
          <div className="bg-[#05080f] border border-white/10 rounded-2xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-white font-semibold text-xs tracking-wider uppercase">
              <FileCode className="w-4 h-4 text-cyan-400" />
              <span>Target Files & Codebase Components</span>
            </div>

            <div className="flex flex-wrap gap-2">
              {(brief?.affected_files && brief.affected_files.length > 0) ? (
                brief.affected_files.map((file, idx) => (
                  <span
                    key={idx}
                    className="font-mono text-xs px-3 py-1.5 rounded-xl bg-[#0c101a] border border-white/10 text-cyan-300 flex items-center gap-1.5 shadow-sm"
                  >
                    <span className="text-emerald-400">#</span>
                    <span>{file}</span>
                  </span>
                ))
              ) : (
                <span className="text-xs text-neutral-400 font-mono">Target components mapped in primary source directory.</span>
              )}
            </div>
          </div>

          {/* Section 3: Surgical 4-Step Implementation Roadmap */}
          <div className="bg-[#05080f] border border-white/10 rounded-2xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-white font-semibold text-xs tracking-wider uppercase">
              <Layers className="w-4 h-4 text-purple-400" />
              <span>Proposed Surgical Fix Roadmap</span>
            </div>

            <div className="space-y-2">
              {(brief?.proposed_plan && brief.proposed_plan.length > 0 ? brief.proposed_plan : [
                `Trace logic in target module related to '${task.issue?.title}'.`,
                "Implement surgical fix preserving public API compatibility and style.",
                "Execute local test suite and add regression test coverage.",
                "Verify clean Git diff security scan (zero credentials or unrelated changes)."
              ]).map((step, idx) => (
                <div key={idx} className="flex items-start gap-3 bg-[#0c101a] p-2.5 rounded-xl border border-white/10">
                  <span className="w-5 h-5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                    {idx + 1}
                  </span>
                  <span className="text-xs text-neutral-300 leading-relaxed">{step}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Section 4: Testing & Verification Strategy */}
          <div className="bg-[#05080f] border border-white/10 rounded-2xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-white font-semibold text-xs tracking-wider uppercase">
                <Terminal className="w-4 h-4 text-emerald-400" />
                <span>Test & Verification Strategy</span>
              </div>
              <span className="text-[11px] text-neutral-400 font-mono">
                {brief?.test_strategy?.runner || 'Standard Test Runner'}
              </span>
            </div>

            <div className="bg-[#0c101a] p-3 rounded-xl border border-white/10 font-mono text-xs text-emerald-400 flex items-center justify-between">
              <code>$ {brief?.test_strategy?.command || 'npm test || pytest'}</code>
              <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Automated
              </span>
            </div>
            <p className="text-[11px] text-neutral-400">
              {brief?.test_strategy?.verification || 'Run project test suite to verify 0 regressions before pull request publication.'}
            </p>
          </div>

          {/* Section 5: Repository Contribution Rule & Automated Decision */}
          <div className={`p-5 rounded-2xl border transition-all ${
            isAssignmentRequired 
              ? 'bg-amber-500/5 border-amber-500/30' 
              : 'bg-emerald-500/5 border-emerald-500/30'
          }`}>
            <div className="flex items-center gap-2 font-bold text-sm mb-2">
              {isAssignmentRequired ? (
                <>
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  <span className="text-amber-300">Repository Rule: Maintainer Pre-Assignment Required</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span className="text-emerald-300">Repository Rule: Direct Contribution Permitted (No Pre-Assignment)</span>
                </>
              )}
            </div>

            <p className="text-xs text-neutral-300 mb-4 leading-relaxed">
              {isAssignmentRequired
                ? 'Contributing guidelines require maintainer approval before coding begins to prevent duplicate work. When you click approve below, the platform will automatically post this assignment request and wait for maintainer confirmation.'
                : 'Repository allows direct branch preparation and pull request submission without prior maintainer assignment. When you click approve below, the platform will immediately prepare your isolated Git worktree & branch and open Antigravity.'}
            </p>

            {/* If assignment required, show editable draft comment */}
            {isAssignmentRequired && (
              <div className="space-y-2">
                <label className="text-[11px] font-semibold text-neutral-400 uppercase tracking-wider block">
                  Draft Assignment Request Comment (Ready to submit upon your approval)
                </label>
                <textarea
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  rows={4}
                  className="w-full bg-[#0c101a] border border-white/10 focus:border-amber-500 rounded-xl p-3 text-xs text-neutral-200 focus:outline-none transition resize-none leading-relaxed"
                  placeholder="Draft comment to maintainers requesting assignment..."
                />
              </div>
            )}
          </div>

        </div>

        {/* Footer Actions ("After that I approve") */}
        <div className="px-6 py-4 border-t border-white/10 bg-[#080c14] flex items-center justify-between gap-4">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="px-4 py-2.5 rounded-xl text-xs font-semibold text-neutral-400 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={handleApproveClick}
            disabled={isSubmitting}
            className={`px-6 py-2.5 rounded-xl text-xs font-bold transition-all shadow-lg flex items-center gap-2 active:scale-95 disabled:opacity-50 ${
              isAssignmentRequired
                ? 'bg-amber-500 hover:bg-amber-400 text-gray-950 shadow-amber-500/20'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/30'
            }`}
          >
            {isSubmitting ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>{isAssignmentRequired ? 'Submitting to GitHub...' : 'Preparing Workspace...'}</span>
              </>
            ) : isAssignmentRequired ? (
              <>
                <Send className="w-4 h-4" />
                <span>Approve & Submit Request to Maintainers</span>
              </>
            ) : (
              <>
                <Check className="w-4 h-4 stroke-[3]" />
                <span>Approve Plan & Launch Workspace</span>
              </>
            )}
          </button>
        </div>

      </div>
    </div>
  );
};
