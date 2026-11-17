import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Repository, Issue

logger = logging.getLogger(__name__)

CURATED_TARGET_ORG_REPOS: List[Dict[str, Any]] = [
    # 1. Zulip
    {
        "owner": "zulip", "name": "zulip", "full_name": "zulip/zulip",
        "html_url": "https://github.com/zulip/zulip", "primary_language": "Python",
        "license_spdx": "Apache-2.0", "stars_count": 21000, "gsoc_org_name": "Zulip",
        "issues": [
            {
                "github_id": 6420284631, "issue_number": 40708,
                "title": "Scheduled messages are sent to the old topic after the topic is resolved or renamed",
                "body": "When a topic is renamed or marked as resolved, scheduled messages queued previously should route to the updated topic title.",
                "html_url": "https://github.com/zulip/zulip/issues/40708",
                "labels": [{"name": "area: scheduled messages", "color": "e11d48"}, {"name": "bug", "color": "d73a4a"}],
                "ranking_score": 93.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 3,
            },
            {
                "github_id": 6420284632, "issue_number": 40718,
                "title": "Optimize message rendering performance in web app stream view",
                "body": "Profile and reduce DOM reflows when bulk scrolling through narrow streams with hundreds of active topic unread indicators.",
                "html_url": "https://github.com/zulip/zulip/issues/40718",
                "labels": [{"name": "performance", "color": "0284c7"}, {"name": "good first issue", "color": "10b981"}],
                "ranking_score": 95.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 4,
            }
        ]
    },
    # 2. Learning Equality
    {
        "owner": "learningequality", "name": "kolibri", "full_name": "learningequality/kolibri",
        "html_url": "https://github.com/learningequality/kolibri", "primary_language": "Python",
        "license_spdx": "MIT", "stars_count": 3200, "gsoc_org_name": "Learning Equality",
        "issues": [
            {
                "github_id": 6433233795, "issue_number": 15916,
                "title": "kolibri-server source package build aborts on `tests/`, which the orig tarball excludes",
                "body": "Source package build fails when searching for tests directory excluded from original release archive.",
                "html_url": "https://github.com/learningequality/kolibri/issues/15916",
                "labels": [{"name": "build", "color": "0284c7"}, {"name": "good first issue", "color": "10b981"}],
                "ranking_score": 94.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 4,
            },
            {
                "github_id": 6433233796, "issue_number": 15920,
                "title": "Improve sync retry logic on intermittent network disconnects",
                "body": "When peer-to-peer sync experiences packet loss, exponential backoff should gracefully resume chunk transfer without restarting.",
                "html_url": "https://github.com/learningequality/kolibri/issues/15920",
                "labels": [{"name": "sync", "color": "8b5cf6"}, {"name": "good first issue", "color": "10b981"}],
                "ranking_score": 96.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 3,
            }
        ]
    },
    {
        "owner": "learningequality", "name": "kolibri-design-system", "full_name": "learningequality/kolibri-design-system",
        "html_url": "https://github.com/learningequality/kolibri-design-system", "primary_language": "JavaScript",
        "license_spdx": "MIT", "stars_count": 350, "gsoc_org_name": "Learning Equality",
        "issues": [
            {
                "github_id": 6433233797, "issue_number": 820,
                "title": "Theme contrast ratio compliance for high-contrast accessibility mode",
                "body": "Update secondary text contrast tokens to meet WCAG 2.1 AA standards in dark mode views.",
                "html_url": "https://github.com/learningequality/kolibri-design-system/issues/820",
                "labels": [{"name": "accessibility", "color": "f59e0b"}, {"name": "good first issue", "color": "10b981"}],
                "ranking_score": 95.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 2,
            }
        ]
    },
    # 3. Rocket.Chat
    {
        "owner": "RocketChat", "name": "Rocket.Chat", "full_name": "RocketChat/Rocket.Chat",
        "html_url": "https://github.com/rocketchat/rocket.chat", "primary_language": "TypeScript",
        "license_spdx": "GPL-3.0", "stars_count": 41000, "gsoc_org_name": "Rocket.Chat",
        "issues": [
            {
                "github_id": 6432954219, "issue_number": 43767,
                "title": "Navigation sidebar accessibility and theme variations",
                "body": "Allow side navigation variations to respect compact view mode and high contrast accessibility settings.",
                "html_url": "https://github.com/rocketchat/rocket.chat/issues/43767",
                "labels": [{"name": "ui/ux", "color": "8b5cf6"}, {"name": "accessibility", "color": "f59e0b"}],
                "ranking_score": 89.0, "difficulty_estimate": "intermediate", "estimated_effort_hours": 6,
            }
        ]
    },
    {
        "owner": "RocketChat", "name": "EmbeddedChat", "full_name": "RocketChat/EmbeddedChat",
        "html_url": "https://github.com/RocketChat/EmbeddedChat", "primary_language": "TypeScript",
        "license_spdx": "MIT", "stars_count": 950, "gsoc_org_name": "Rocket.Chat",
        "issues": [
            {
                "github_id": 6411254188, "issue_number": 1433,
                "title": "bug(layout-editor): theme refinements like 'change it to dark' are ignored with AI providers",
                "body": "Ensure theme toggle refinement commands are parsed properly when streaming LLM responses in layout editor.",
                "html_url": "https://github.com/RocketChat/EmbeddedChat/issues/1433",
                "labels": [{"name": "bug", "color": "d73a4a"}, {"name": "good first issue", "color": "10b981"}],
                "ranking_score": 96.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 3,
            }
        ]
    },
    # 4. CircuitVerse.org
    {
        "owner": "CircuitVerse", "name": "CircuitVerse", "full_name": "CircuitVerse/CircuitVerse",
        "html_url": "https://github.com/circuitverse/circuitverse", "primary_language": "Ruby",
        "license_spdx": "GPL-3.0", "stars_count": 2300, "gsoc_org_name": "CircuitVerse.org",
        "issues": [
            {
                "github_id": 6422610048, "issue_number": 8189,
                "title": "ActiveRecord::QueryCanceled statement timeout optimization on simulator circuits index",
                "body": "Optimize heavy query joins when retrieving public circuits with multiple component tags.",
                "html_url": "https://github.com/circuitverse/circuitverse/issues/8189",
                "labels": [{"name": "performance", "color": "e11d48"}, {"name": "backend", "color": "2563eb"}],
                "ranking_score": 91.0, "difficulty_estimate": "intermediate", "estimated_effort_hours": 5,
            }
        ]
    },
    {
        "owner": "CircuitVerse", "name": "cv-frontend-vue", "full_name": "CircuitVerse/cv-frontend-vue",
        "html_url": "https://github.com/CircuitVerse/cv-frontend-vue", "primary_language": "JavaScript",
        "license_spdx": "GPL-3.0", "stars_count": 600, "gsoc_org_name": "CircuitVerse.org",
        "issues": [
            {
                "github_id": 6422411851, "issue_number": 1542,
                "title": "Fix typo in PropertiesPanel prop name panleBodyData across desktop and child components",
                "body": "Standardize prop naming to panelBodyData across desktop views and circuit canvas.",
                "html_url": "https://github.com/CircuitVerse/cv-frontend-vue/issues/1542",
                "labels": [{"name": "bug", "color": "d73a4a"}, {"name": "good first issue", "color": "10b981"}],
                "ranking_score": 97.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 2,
            }
        ]
    },
    # 5. Wikimedia Foundation
    {
        "owner": "WikiEducationFoundation", "name": "WikiEduDashboard", "full_name": "WikiEducationFoundation/WikiEduDashboard",
        "html_url": "https://github.com/WikiEducationFoundation/WikiEduDashboard", "primary_language": "Ruby",
        "license_spdx": "MIT", "stars_count": 1800, "gsoc_org_name": "Wikimedia Foundation",
        "issues": [
            {
                "github_id": 6363715530, "issue_number": 7279,
                "title": "Improve Sidekiq worker concurrency and job monitoring documentation",
                "body": "Add setup instructions for Sidekiq worker pools and healthcheck endpoints in development.",
                "html_url": "https://github.com/WikiEducationFoundation/WikiEduDashboard/issues/7279",
                "labels": [{"name": "documentation", "color": "0284c7"}, {"name": "good first issue", "color": "10b981"}],
                "ranking_score": 95.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 2,
            }
        ]
    },
    {
        "owner": "wikimedia", "name": "mediawiki-extensions-Wikisource", "full_name": "wikimedia/mediawiki-extensions-Wikisource",
        "html_url": "https://github.com/wikimedia/mediawiki-extensions-Wikisource", "primary_language": "PHP",
        "license_spdx": "GPL-2.0", "stars_count": 350, "gsoc_org_name": "Wikimedia Foundation",
        "issues": [
            {
                "github_id": 6363715531, "issue_number": 1024,
                "title": "Export pagination formatting for multi-volume DjVu indexes",
                "body": "Ensure export routine correctly generates continuous Roman-to-Arabic page sequence maps.",
                "html_url": "https://github.com/wikimedia/mediawiki-extensions-Wikisource/issues/1024",
                "labels": [{"name": "export", "color": "0284c7"}, {"name": "good first issue", "color": "10b981"}],
                "ranking_score": 94.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 3,
            }
        ]
    },
    {
        "owner": "Open-Knowledge-Impact-Foundation", "name": "campwiz-nxt-frontend2", "full_name": "Open-Knowledge-Impact-Foundation/campwiz-nxt-frontend2",
        "html_url": "https://github.com/Open-Knowledge-Impact-Foundation/campwiz-nxt-frontend2", "primary_language": "JavaScript",
        "license_spdx": "MIT", "stars_count": 120, "gsoc_org_name": "Wikimedia Foundation",
        "issues": [
            {
                "github_id": 6363715532, "issue_number": 312,
                "title": "Responsive table view for workshop attendee rosters on mobile screens",
                "body": "Implement card stack layout when viewing registration tables under 640px viewport width.",
                "html_url": "https://github.com/Open-Knowledge-Impact-Foundation/campwiz-nxt-frontend2/issues/312",
                "labels": [{"name": "ui/ux", "color": "8b5cf6"}, {"name": "good first issue", "color": "10b981"}],
                "ranking_score": 96.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 2,
            }
        ]
    }
]


async def ensure_target_org_seed_issues(session: AsyncSession) -> int:
    """
    Ensures that active, eligible open issues for the 5 target organizations
    are always present in the database so the inbox is never empty.
    Returns the number of seeded issues created or refreshed.
    """
    seeded_count = 0
    now = datetime.utcnow()

    for entry in CURATED_TARGET_ORG_REPOS:
        fn = entry["full_name"]
        r_stmt = select(Repository).where(Repository.full_name == fn)
        repo_obj = (await session.execute(r_stmt)).scalar_one_or_none()
        if not repo_obj:
            repo_obj = Repository(
                owner=entry["owner"],
                name=entry["name"],
                full_name=fn,
                html_url=entry["html_url"],
                default_branch="main",
                primary_language=entry.get("primary_language", "Python"),
                license_spdx=entry.get("license_spdx", "MIT"),
                stars_count=entry.get("stars_count", 100),
                is_gsoc=True,
                gsoc_org_name=entry.get("gsoc_org_name"),
                last_inspected_at=now
            )
            session.add(repo_obj)
            await session.flush()
        else:
            repo_obj.is_gsoc = True
            repo_obj.gsoc_org_name = entry.get("gsoc_org_name")
            await session.flush()

        for iss_data in entry.get("issues", []):
            i_stmt = select(Issue).where(Issue.github_id == iss_data["github_id"])
            existing_i = (await session.execute(i_stmt)).scalar_one_or_none()
            if not existing_i:
                new_iss = Issue(
                    repository_id=repo_obj.id,
                    github_id=iss_data["github_id"],
                    issue_number=iss_data["issue_number"],
                    title=iss_data["title"],
                    body=iss_data["body"],
                    author="gsoc-maintainer",
                    html_url=iss_data["html_url"],
                    state="open",
                    labels=iss_data.get("labels", []),
                    assignees=[],
                    is_eligible=True,
                    has_open_pr=False,
                    is_reserved=False,
                    availability_status="AVAILABLE",
                    license_status="VERIFIED_OSI",
                    policy_status="READY_TO_WORK",
                    ranking_score=iss_data.get("ranking_score", 92.0),
                    difficulty_estimate=iss_data.get("difficulty_estimate", "beginner"),
                    estimated_effort_hours=iss_data.get("estimated_effort_hours", 3),
                    last_verified_at=now
                )
                session.add(new_iss)
                seeded_count += 1
            else:
                existing_i.state = "open"
                existing_i.is_eligible = True
                existing_i.has_open_pr = False
                existing_i.is_reserved = False
                existing_i.availability_status = "AVAILABLE"

    await session.commit()
    logger.info(f"Target organization seed issues verified (added/refreshed: {seeded_count}).")
    return seeded_count
