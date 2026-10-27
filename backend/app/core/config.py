import os
from pathlib import Path
from typing import List, Optional

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
HOME_DIR = Path.home()
DEFAULT_DATA_DIR = HOME_DIR / ".issue_to_pr"
DEFAULT_WORKSPACE_DIR = DEFAULT_DATA_DIR / "workspaces"
DEFAULT_REPOS_CACHE_DIR = DEFAULT_DATA_DIR / "cache" / "repos"

def _get_github_token() -> Optional[str]:
    token = os.getenv("GITHUB_TOKEN")
    if token and token.strip():
        return token.strip()
    import shutil
    import subprocess
    if shutil.which("gh"):
        try:
            res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
    return None

class Settings:
    PROJECT_NAME: str = "Issue-to-PR Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql+asyncpg://{os.getenv('USER', 'shahi')}@localhost:5432/issuetopr"
    )
    SQLITE_FALLBACK_URL: str = f"sqlite+aiosqlite:///{DEFAULT_DATA_DIR}/issuetopr.db"
    
    # GitHub Integration
    GITHUB_TOKEN: Optional[str] = _get_github_token()
    GITHUB_API_BASE: str = "https://api.github.com"
    GITHUB_API_VERSION: str = "2022-11-28"
    
    # Workspace & Worktree
    DATA_DIR: Path = DEFAULT_DATA_DIR
    WORKSPACE_ROOT: Path = DEFAULT_WORKSPACE_DIR
    REPOS_CACHE_DIR: Path = DEFAULT_REPOS_CACHE_DIR
    
    # Antigravity Desktop App locations on macOS
    ANTIGRAVITY_APP_PATHS: List[str] = [
        "/Applications/Antigravity.app",
        "/Applications/Antigravity IDE.app",
        str(HOME_DIR / "Applications/Antigravity.app"),
    ]
    AGY_CLI_PATH: Optional[str] = os.getenv("AGY_CLI_PATH", str(HOME_DIR / ".local/bin/agy"))
    
    # Auto-publishing policy (Default false until user explicitly toggles in settings)
    AUTO_PUBLISH_DEFAULT: bool = False
    
    # Default skills profile
    DEFAULT_SKILLS: List[str] = [
        "python",
        "typescript",
        "javascript",
        "fastapi",
        "react",
        "nodejs",
        "tailwindcss",
        "postgresql",
        "sql",
        "docker",
        "kubernetes",
        "github-actions",
        "ai",
        "machine-learning"
    ]
    
    # Discovery defaults
    DISCOVERY_LANGUAGES: List[str] = ["python", "typescript", "javascript", "go", "rust"]
    DISCOVERY_LABELS: List[str] = ["good first issue", "help wanted", "bug", "enhancement"]
    BLOCKED_LABELS: List[str] = ["wontfix", "invalid", "duplicate", "blocked", "claimed", "in progress"]

settings = Settings()

# Ensure directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
settings.REPOS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
