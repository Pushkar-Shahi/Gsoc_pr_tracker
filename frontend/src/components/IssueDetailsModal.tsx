import React, { useState } from 'react';
import { 
  X, ExternalLink, Zap, Shield, FileText, CheckCircle2, 
  AlertTriangle, Clock, Star, GitBranch, ArrowRight, User, Check 
} from 'lucide-react';
import { Issue } from '../types';
import { useLockBodyScroll } from '../hooks/useLockBodyScroll';

interface IssueDetailsModalProps {
  issue: Issue | null;
  onClose: () => void;
  onSelectIssue: (issueId: string) => void;
  onCompleteIssue?: (issueId: string) => void;
}

export const IssueDetailsModal: React.FC<IssueDetailsModalProps> = ({
  issue,
  onClose,
  onSelectIssue,
  onCompleteIssue,
}) => {
  useLockBodyScroll(Boolean(issue));

  const [activeTab, setActiveTab] = useState<'problem' | 'ranking' | 'policy'>('problem');
  const breakdown = issue?.ranking_breakdown;

  if (!issue) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="bg-[#0c101a] border border-white/15 rounded-t-3xl sm:rounded-2xl w-full max-w-4xl max-h-[92vh] sm:max-h-[88vh] flex flex-col shadow-2xl overflow-hidden">
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
          {activeTab === 'problem' && (
            <div className="space-y-4">
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
