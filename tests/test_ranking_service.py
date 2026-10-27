import pytest
from app.services.ranking_service import RankingService

def test_ranking_skill_match_python():
    service = RankingService(user_skills=["python", "fastapi", "docker"])
    eval_res = service.evaluate_issue(
        title="Fix FastAPI dependency injection bug in router",
        body="Here are the reproduction steps:\n```python\ndef test(): pass\n```\nExpected behavior: works.",
        labels=[{"name": "bug"}, {"name": "good first issue"}],
        repo_language="Python",
        repo_stars=5000,
        license_spdx="MIT"
    )

    assert eval_res["ranking_score"] >= 70.0
    assert eval_res["difficulty_estimate"] == "beginner"
    assert eval_res["ranking_breakdown"]["skill_match"] > 15.0
    assert any("FastAPI" in r or "Python" in r for r in eval_res["ranking_breakdown"]["reasons"])

def test_ranking_detects_blocker_labels():
    service = RankingService(user_skills=["python"])
    eval_res = service.evaluate_issue(
        title="Some complex feature",
        body="Short text",
        labels=[{"name": "blocked"}, {"name": "wontfix"}],
        repo_language="Python",
        repo_stars=10,
        license_spdx=None
    )

    assert eval_res["ranking_breakdown"]["has_blocker_risk"] is True
    assert any("blocker" in r.lower() for r in eval_res["ranking_breakdown"]["reasons"])

def test_ranking_never_rejects_issues():
    service = RankingService(user_skills=["go", "rust"])
    eval_res = service.evaluate_issue(
        title="Unrelated issue in strange language",
        body="minimal",
        labels=[],
        repo_language="Cobol",
        repo_stars=1,
        license_spdx=None
    )

    assert eval_res["ranking_score"] > 0
    assert "ranking_breakdown" in eval_res
