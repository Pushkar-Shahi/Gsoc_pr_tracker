import re
from typing import Dict, Any, List, Optional
from app.core.config import settings


def _clamp_weight(val: Any) -> float:
    try:
        return max(0.25, min(3.0, float(val)))
    except Exception:
        return 1.0


class RankingService:
    def __init__(
        self,
        user_skills: Optional[List[str]] = None,
        skill_weights: Optional[Dict[str, float]] = None,
        tag_weights: Optional[Dict[str, float]] = None,
    ):
        self.skills = [s.lower() for s in (user_skills or settings.DEFAULT_SKILLS)]
        self.skill_weights = {str(k).lower().strip(): _clamp_weight(v) for k, v in (skill_weights or {}).items()}
        self.tag_weights = {str(k).lower().strip(): _clamp_weight(v) for k, v in (tag_weights or {}).items()}

    def evaluate_issue(
        self,
        title: str,
        body: str,
        labels: List[Any],
        repo_language: str,
        repo_stars: int = 0,
        license_spdx: str = None
    ) -> Dict[str, Any]:
        """
        Computes an explainable score (0-100), difficulty estimate,
        estimated effort hours, and detailed justification.
        """
        title_lower = (title or "").lower()
        body_lower = (body or "").lower()
        label_names = [
            (lbl["name"].lower() if isinstance(lbl, dict) else str(lbl).lower())
            for lbl in labels
        ]
        
        reasons = []
        
        # 1. Skill & Language Match (Max 35 points)
        skill_score = 0.0
        matched_skills = []
        
        if repo_language and repo_language.lower() in self.skills:
            lang_w = self.skill_weights.get(repo_language.lower(), 1.0)
            skill_score += 20.0 * lang_w
            matched_skills.append(repo_language)
            reasons.append(f"Repository primary language '{repo_language}' matches your toolbox ({lang_w:.1f}x weight).")
        
        for skill in self.skills:
            if skill == (repo_language or "").lower():
                continue
            skill_w = self.skill_weights.get(skill, 1.0)
            # Check title, body, and labels for technology mention
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, title_lower) or any(re.search(pattern, l) for l in label_names):
                skill_score += 5.0 * skill_w
                matched_skills.append(skill)
            elif re.search(pattern, body_lower):
                skill_score += 2.0 * skill_w
                matched_skills.append(skill)
        
        skill_score = min(skill_score, 35.0)
        if matched_skills:
            unique_matches = list(set(matched_skills))[:5]
            reasons.append(f"Matched toolbox skills: {', '.join(unique_matches)}.")
        else:
            reasons.append("Limited direct match with configured toolbox skills.")

        # 2. Problem Statement Clarity & Acceptance Criteria (Max 25 points)
        clarity_score = 0.0
        body_len = len(body_lower)
        
        if body_len > 150:
            clarity_score += 8.0
        elif body_len > 50:
            clarity_score += 4.0
        else:
            reasons.append("Issue description is very short; acceptance criteria may need clarification.")

        # Code blocks or stack traces
        if "```" in (body or ""):
            clarity_score += 7.0
            reasons.append("Includes structured code blocks or stack traces.")
            
        # Reproduction steps or checklist items
        if any(marker in body_lower for marker in ["steps to reproduce", "expected behavior", "repro", "acceptance criteria", "- [ ]", "error:"]):
            clarity_score += 10.0
            reasons.append("Contains structured reproduction steps or explicit acceptance criteria.")
        
        clarity_score = min(clarity_score, 25.0)

        # 3. Repository Health & Contribution Readiness (Max 20 points)
        health_score = 0.0
        if repo_stars >= 1000:
            health_score += 8.0
            reasons.append(f"High community health and active project ({repo_stars:,} stars).")
        elif repo_stars >= 50:
            health_score += 5.0
        else:
            health_score += 3.0

        # Verified OSI license
        osi_licenses = ["mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "mpl-2.0", "gpl-3.0", "lgpl-3.0"]
        if license_spdx and license_spdx.lower() in osi_licenses:
            health_score += 8.0
            reasons.append(f"Verified open-source license: {license_spdx}.")
        elif license_spdx:
            health_score += 4.0
            reasons.append(f"License present ({license_spdx}), verify contribution compatibility.")
        else:
            reasons.append("License not verified; caution recommended before contribution.")

        # Friendly contributor labels + custom tag weighting matrix
        matched_tag_weights: Dict[str, float] = {}
        tag_bonus = 0.0
        for lbl in label_names:
            if lbl in self.tag_weights:
                w = self.tag_weights[lbl]
                matched_tag_weights[lbl] = w
                tag_bonus += 3.0 * (w - 1.0)
        if any(l in ["good first issue", "beginner friendly", "easy", "help wanted"] for l in label_names):
            health_score += 4.0
            reasons.append("Flagged with maintainer 'help wanted' or 'good first issue' label.")
        if matched_tag_weights:
            reasons.append(f"Custom tag weights applied: {', '.join(f'{k} ({v:.1f}x)' for k, v in matched_tag_weights.items())}.")

        health_score = max(0.0, min(health_score + tag_bonus, 20.0))

        # 4. Implementation Effort & Scope (Max 20 points)
        effort_score = 15.0
        difficulty = "intermediate"
        estimated_hours = 4.0

        if any(l in ["good first issue", "documentation", "docs", "typo", "minor", "small"] for l in label_names):
            difficulty = "beginner"
            estimated_hours = 2.0
            effort_score = 20.0
            reasons.append("Estimated as beginner/approachable effort based on issue scope.")
        elif any(l in ["architecture", "refactor", "epic", "breaking change", "security", "complex"] for l in label_names) or body_len > 4000:
            difficulty = "advanced"
            estimated_hours = 12.0
            effort_score = 8.0
            reasons.append("Higher complexity or large scope indicated.")
        else:
            difficulty = "intermediate"
            estimated_hours = 5.0
            effort_score = 14.0

        # Blocker and Risk Check
        blocker_risk = False
        if any(l in ["wontfix", "blocked", "duplicate", "invalid", "in progress"] for l in label_names):
            blocker_risk = True
            reasons.append("Caution: Label indicates potential blocker or duplicate work.")
            effort_score = max(0.0, effort_score - 10.0)

        total_score = round(skill_score + clarity_score + health_score + effort_score, 1)
        total_score = max(5.0, min(total_score, 98.0))

        # Generate a concise AI-style summary
        summary = self._generate_summary(title, body, label_names, repo_language)

        return {
            "ranking_score": total_score,
            "difficulty_estimate": difficulty,
            "estimated_effort_hours": estimated_hours,
            "ai_summary": summary,
            "ranking_breakdown": {
                "skill_match": round(skill_score, 1),
                "clarity_score": round(clarity_score, 1),
                "repo_health_score": round(health_score, 1),
                "effort_score": round(effort_score, 1),
                "reasons": reasons,
                "has_blocker_risk": blocker_risk,
                "matched_skills": list(set(matched_skills)),
                "weighted_matrix_applied": bool(self.skill_weights or self.tag_weights),
                "matched_tag_weights": matched_tag_weights,
            }
        }

    def _generate_summary(self, title: str, body: str, labels: List[str], language: str) -> str:
        clean_title = title.strip()
        body_first_lines = " ".join([l.strip() for l in (body or "").split("\n") if l.strip() and not l.startswith("#")][:3])
        snippet = (body_first_lines[:240] + "...") if len(body_first_lines) > 240 else body_first_lines
        lang_str = f" in {language}" if language else ""
        return f"Issue focuses on '{clean_title}'{lang_str}. Context: {snippet or 'No additional details provided in issue description.'}"
