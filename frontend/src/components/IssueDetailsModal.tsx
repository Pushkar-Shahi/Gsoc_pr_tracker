import React, { useState, useEffect } from 'react';
import { 
  X, ExternalLink, Zap, Shield, FileText, CheckCircle2, 
  AlertTriangle, Clock, Star, GitBranch, ArrowRight, User, Check,
  Lock, GitPullRequest, RefreshCw, Loader2
} from 'lucide-react';
import { Issue } from '../types';
import { fetchLiveIssueAvailability } from '../api';
import { useLockBodyScroll } from '../hooks/useLockBodyScroll';

interface IssueDetailsModalProps {
  issue: Issue | null;
  onClose: () => void;
  onSelectIssue: (issueId: string) => void;
  onCompleteIssue?: (issueId: string) => void;
}

export const IssueDetailsModal: React.FC<IssueDetailsModalProps> = ({
  issue: initialIssue,
  onClose,
  onSelectIssue,
  onCompleteIssue,
}) => {
  useLockBodyScroll(Boolean(initialIssue));

  const [activeTab, setActiveTab] = useState<'problem' | 'ranking' | 'policy'>('problem');
  const [issue, setIssue] = useState<Issue | null>(initialIssue);
  const [isRechecking, setIsRechecking] = useState(false);
  const [recheckMessage, setRecheckMessage] = useState<string | null>(null);

  useEffect(() => {
    setIssue(initialIssue);
    setRecheckMessage(null);
  }, [initialIssue]);

  const handleLiveRecheck = async () => {
    if (!issue) return;
    setIsRechecking(true);
    setRecheckMessage(null);
    try {
      const refreshed = await fetchLiveIssueAvailability(issue.id);
      setIssue(refreshed);
      if (refreshed.has_open_pr) {
        setRecheckMessage(`Detected ${refreshed.linked_pr_count} active open PR(s) pending review.`);
      } else if (refreshed.is_reserved) {
        setRecheckMessage('Verified: Issue is reserved for maintainers.');
      } else {
        setRecheckMessage('Verified: Issue is clean, unassigned, and open for contributions!');
      }
    } catch {
      setRecheckMessage('Could not connect to GitHub to re-verify.');
    } finally {
      setIsRechecking(false);
    }
  };

  const breakdown = issue?.ranking_breakdown;

  if (!issue) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/80 backdrop-blur-xs animate-fade-in">
      <div className="bg-[#0c101a] border border-white/15 rounded-t-3xl sm:rounded-2xl w-full max-w-4xl max-h-[92vh] sm:max-h-[88vh] flex flex-col shadow-2xl overflow-hidden animate-slide-up sm:animate-scale-up">
        {/* Modal Header */}
        <div className="px-4 sm:px-6 py-3.5 sm:py-4 border-b border-white/10 flex items-center justify-between bg-[#080c14]">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs px-2.5 py-1 rounded-lg bg-neutral-900 border border-white/20 text-white font-semibold">
              {issue.repository?.full_name}
            </span>
            {(issue.repository?.is_gsoc || issue.repository?.gsoc_org_name) && (
              <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-neutral-900 text-neutral-200 border border-white/20 shadow-sm">
                <span className="text-xs">🎓</span>
                <span>GSoC: {issue.repository?.gsoc_org_name || 'GSoC Org'}</span>
              </span>
            )}
            <span className="text-xs text-neutral-400">Issue #{issue.issue_number}</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleLiveRecheck}
              disabled={isRechecking}
              className="text-xs text-neutral-300 hover:text-white flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-neutral-900 hover:bg-neutral-800 border border-white/10 transition disabled:opacity-50"
              title="Query GitHub in real time for new pull requests and maintainer status"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRechecking ? 'animate-spin text-blue-400' : ''}`} />
              <span className="hidden sm:inline">{isRechecking ? 'Checking GitHub...' : 'Re-check PRs'}</span>
            </button>
            <a
              href={issue.html_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-neutral-300 hover:text-white flex items-center gap-1 px-2.5 py-1 rounded-xl bg-neutral-900 hover:bg-neutral-800 border border-white/10 transition"
            >
              <span>GitHub</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
            <button
              onClick={onClose}
              className="p-1 rounded-xl text-neutral-400 hover:text-white hover:bg-neutral-900 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Title & Navigation Tabs */}
        <div className="px-4 sm:px-6 pt-4 sm:pt-5 pb-2 border-b border-white/10 bg-[#080c14]">
          <h2 className="text-base sm:text-lg font-bold text-white mb-3 sm:mb-4">
            #{issue.issue_number} — {issue.title}
          </h2>

          <div className="flex items-center gap-4 text-xs font-medium overflow-x-auto no-scrollbar">
            <button
              onClick={() => setActiveTab('problem')}
              className={`pb-2 border-b-2 transition whitespace-nowrap ${
                activeTab === 'problem'
                  ? 'border-white text-white font-bold'
                  : 'border-transparent text-neutral-400 hover:text-neutral-200'
              }`}
            >
              Problem Statement
            </button>

            <button
              onClick={() => setActiveTab('ranking')}
              className={`pb-2 border-b-2 transition flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === 'ranking'
                  ? 'border-white text-white font-bold'
                  : 'border-transparent text-neutral-400 hover:text-neutral-200'
              }`}
            >
              <Zap className="w-3.5 h-3.5" />
              <span>Explainable AI Ranking ({issue.ranking_score.toFixed(0)})</span>
            </button>

            <button
              onClick={() => setActiveTab('policy')}
              className={`pb-2 border-b-2 transition flex items-center gap-1.5 whitespace-nowrap ${
                activeTab === 'policy'
                  ? 'border-white text-white font-bold'
                  : 'border-transparent text-neutral-400 hover:text-neutral-200'
              }`}
            >
              <Shield className="w-3.5 h-3.5" />
              <span>Rules & Policy</span>
            </button>
          </div>
        </div>

        {/* Modal Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 text-sm text-gray-300">
          {recheckMessage && (
            <div className="p-3 rounded-xl bg-blue-950/30 border border-blue-500/30 text-blue-300 text-xs flex items-center justify-between">
              <span>{recheckMessage}</span>
              <button onClick={() => setRecheckMessage(null)} className="text-neutral-400 hover:text-white text-xs">✕</button>
            </div>
          )}

          {activeTab === 'problem' && (
            <div className="space-y-4">
              {/* Issue Availability Status Banner */}
              {issue.is_reserved ? (
                <div className="bg-rose-950/20 border border-rose-500/40 rounded-xl p-4 text-rose-300 space-y-1">
                  <div className="flex items-center gap-2 text-xs font-bold text-rose-400">
                    <Lock className="w-4 h-4" />
                    <span>Reserved for Maintainer Implementation</span>
                  </div>
                  <p className="text-xs text-rose-200/90 leading-relaxed">
                    This issue has been marked by maintainers as internal/reserved ({issue.reservation_reason || 'maintainer-only'}). Pull requests submitted by outside contributors will be closed.
                  </p>
                </div>
              ) : issue.has_open_pr && issue.linked_prs && issue.linked_prs.length > 0 ? (
                <div className="bg-amber-950/25 border border-amber-500/40 rounded-xl p-4 text-amber-200 space-y-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-xs font-bold text-amber-400">
                      <GitPullRequest className="w-4 h-4" />
                      <span>Active Pull Request Pending Review ({issue.linked_prs.length})</span>
                    </div>
                    <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold">
                      PR Already Submitted
                    </span>
                  </div>
                  <p className="text-xs text-amber-100/90 leading-relaxed">
                    A contributor has already submitted an open pull request attempting to close this issue. Maintainers usually close duplicate PRs. Check the existing PR before spending time on this issue:
                  </p>
                  <div className="space-y-2 pt-1">
                    {issue.linked_prs.map((pr) => (
                      <div key={pr.number} className="flex items-center justify-between p-2.5 rounded-lg bg-black/40 border border-amber-500/20 text-xs">
                        <div className="flex items-center gap-2 overflow-hidden">
                          <span className="font-mono text-amber-400 font-bold shrink-0">#{pr.number}</span>
                          <span className="truncate text-white font-medium">{pr.title}</span>
                          {pr.author && <span className="text-neutral-400 text-[11px] shrink-0">by @{pr.author}</span>}
                        </div>
                        <a
                          href={pr.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="ml-3 shrink-0 text-amber-400 hover:text-amber-300 font-semibold underline text-xs inline-flex items-center gap-1"
                        >
                          <span>Inspect PR</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              ) : issue.assignees && issue.assignees.length > 0 ? (
                <div className="bg-purple-950/20 border border-purple-500/30 rounded-xl p-3 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2 text-purple-300 font-medium">
                    <User className="w-4 h-4 text-purple-400" />
                    <span>Assigned to {issue.assignees.map((a: any) => typeof a === 'string' ? a : a.login).join(', ')}</span>
                  </div>
                  <span className="text-[11px] text-purple-300/80">Check with assignee before starting</span>
                </div>
              ) : (
                <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-xl p-3 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2 text-emerald-400 font-semibold">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Ready to Work: Clean, Unassigned, & No Active Pull Requests</span>
                  </div>
                  <span className="text-[11px] text-emerald-300/80">Available for PR</span>
                </div>
              )}

              {/* AI Objective Summary */}
              {issue.ai_summary && (
                <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-xl p-4">
                  <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400 mb-1">
                    <Zap className="w-3.5 h-3.5" />
                    <span>AI Context Brief</span>
                  </div>
                  <p className="text-xs text-gray-300 leading-relaxed">
                    {issue.ai_summary}
                  </p>
                </div>
              )}

              {/* Author & Metadata */}
              <div className="flex flex-wrap items-center gap-4 text-xs text-neutral-400 pb-2 border-b border-white/10">
                <span className="flex items-center gap-1">
                  <User className="w-3.5 h-3.5 text-neutral-500" />
                  <span>Author: {issue.author || 'Unknown'}</span>
                </span>
                <span>Comments: {issue.comments_count}</span>
                <span>Eligibility: Open & Unassigned (Verified)</span>
              </div>

              {/* Original Markdown Body */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400 mb-2">
                  Original Issue Content
                </h3>
                <div className="bg-[#05080f] border border-white/10 rounded-xl p-4 whitespace-pre-wrap font-sans text-xs leading-relaxed text-neutral-300 max-h-96 overflow-y-auto">
                  {issue.body || 'No description provided in this issue.'}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'ranking' && (
            <div className="space-y-6">
              {/* Overall Score Header */}
              <div className="bg-[#05080f] border border-white/10 rounded-xl p-4 flex items-center justify-between">
                <div>
                  <h4 className="font-semibold text-white">Suitability Score: {issue.ranking_score.toFixed(1)} / 100</h4>
                  <p className="text-xs text-neutral-400 mt-0.5">
                    Calculated using transparent criteria matching your skills, problem clarity, repo activity, and effort.
                  </p>
                </div>
                <div className="text-right">
                  <span className="text-xs text-neutral-400 font-medium">Difficulty: </span>
                  <span className="text-xs font-bold text-emerald-400 uppercase">{issue.difficulty_estimate}</span>
                </div>
              </div>

              {/* Score Breakdown Grid */}
              {breakdown && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="bg-[#0c101a] border border-white/10 rounded-xl p-3">
                    <span className="text-[11px] text-neutral-400">Skill Match</span>
                    <p className="text-lg font-bold text-emerald-400 mt-1">{breakdown.skill_match} / 35</p>
                  </div>
                  <div className="bg-[#0c101a] border border-white/10 rounded-xl p-3">
                    <span className="text-[11px] text-neutral-400">Problem Clarity</span>
                    <p className="text-lg font-bold text-cyan-400 mt-1">{breakdown.clarity_score} / 25</p>
                  </div>
                  <div className="bg-[#0c101a] border border-white/10 rounded-xl p-3">
                    <span className="text-[11px] text-neutral-400">Repo Health</span>
                    <p className="text-lg font-bold text-blue-400 mt-1">{breakdown.repo_health_score} / 20</p>
                  </div>
                  <div className="bg-[#0c101a] border border-white/10 rounded-xl p-3">
                    <span className="text-[11px] text-neutral-400">Effort & Scope</span>
                    <p className="text-lg font-bold text-amber-400 mt-1">{breakdown.effort_score} / 20</p>
                  </div>
                </div>
              )}

              {/* Justification Reasons */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-400 mb-3">
                  Scoring Rationale & Evidence
                </h4>
                <div className="space-y-2">
                  {breakdown?.reasons?.map((reason: string, idx: number) => (
                    <div key={idx} className="flex items-start gap-2 bg-[#05080f] p-3 rounded-xl border border-white/10 text-xs text-neutral-300">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                      <span>{reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'policy' && (
            <div className="space-y-6">
              {/* License Card */}
              <div className="bg-[#05080f] border border-white/10 rounded-xl p-4">
                <div className="flex items-center gap-2 text-white font-semibold mb-2">
                  <Shield className="w-4 h-4 text-emerald-400" />
                  <span>Open-Source Licensing Verification</span>
                </div>
                <div className="text-xs text-neutral-300 space-y-2">
                  <p>
                    <span className="text-neutral-400">License Status:</span>{' '}
                    <span className="font-semibold text-emerald-400">{issue.license_status}</span>
                  </p>
                  <p>
                    <span className="text-neutral-400">SPDX Identifier:</span>{' '}
                    <span className="font-mono text-neutral-200">{issue.repository?.license_spdx || 'None detected'}</span>
                  </p>
                  <p className="text-neutral-400 text-[11px]">
                    Public visibility alone does not grant copyright permission to reuse code. The platform ensures only repositories with verifiable open-source policies proceed to workspace preparation without warnings.
                  </p>
                </div>
              </div>

              {/* Assignment Policy State */}
              <div className="bg-[#05080f] border border-white/10 rounded-xl p-4">
                <div className="flex items-center gap-2 text-white font-semibold mb-2">
                  <FileText className="w-4 h-4 text-cyan-400" />
                  <span>Contribution Preflight Policy</span>
                </div>
                <p className="text-xs text-neutral-300 mb-2">
                  Current policy state: <span className="font-bold text-white">{issue.policy_status}</span>
                </p>
                <div className="text-xs text-neutral-400 leading-relaxed bg-[#0c101a] p-3 rounded-lg border border-white/10">
                  {issue.policy_status === 'ASSIGNMENT_REQUIRED' ? (
                    <p className="text-blue-300">
                      Repository instructions require maintainer approval before coding begins. The platform will draft an assignment comment for your review before workspace preparation.
                    </p>
                  ) : (
                    <p className="text-emerald-300">
                      No prior assignment prerequisite detected. Direct branch preparation in Antigravity is permitted.
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-4 sm:px-6 py-3.5 sm:py-4 border-t border-white/10 bg-[#080c14] flex items-center justify-between">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-medium text-neutral-300 hover:text-white bg-neutral-900 hover:bg-neutral-800 border border-white/15 transition active:scale-95"
          >
            Close
          </button>

          <div className="flex items-center gap-2 sm:gap-3">
            {onCompleteIssue && (
              <button
                type="button"
                onClick={() => {
                  onCompleteIssue(issue.id);
                  onClose();
                }}
                className="px-3.5 py-2 rounded-xl text-xs font-semibold text-white bg-neutral-900 hover:bg-neutral-800 border border-white/20 transition flex items-center gap-1.5 active:scale-95 shadow-sm"
                title="Mark as completed & remove from inbox"
              >
                <Check className="w-4 h-4 stroke-[2.5]" />
                <span>Mark Completed</span>
              </button>
            )}

            <button
              onClick={() => {
                onClose();
                onSelectIssue(issue.id);
              }}
              className="px-4 sm:px-5 py-2 rounded-xl bg-white hover:bg-neutral-200 text-black text-xs font-bold shadow-md active:scale-95 transition flex items-center gap-2"
            >
              <span>Select & Start Working</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
