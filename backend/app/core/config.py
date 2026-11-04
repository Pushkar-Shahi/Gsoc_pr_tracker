import os
from pathlib import Path
from typing import List, Optional

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
HOME_DIR = Path.home()
DEFAULT_DATA_DIR = HOME_DIR / ".issue_to_pr"
DEFAULT_WORKSPACE_DIR = DEFAULT_DATA_DIR / "workspaces"
DEFAULT_REPOS_CACHE_DIR = DEFAULT_DATA_DIR / "cache" / "repos"

# Load local environment configuration (.env)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR.parent / ".env")
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

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
def _get_secret_key_default() -> str:
    return os.getenv("SECRET_KEY", "issuetopr_secure_jwt_secret_mwps_2026")

def _normalize_database_url() -> str:
    raw_url = os.getenv(
        "DATABASE_URL",
        f"postgresql+asyncpg://{os.getenv('USER', 'shahi')}@localhost:5432/issuetopr"
    )
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://") and not raw_url.startswith("postgresql+asyncpg://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url

class _SecretKeyDescriptor:
    def __init__(self, default_factory):
        self.default_factory = default_factory
        self.val = None

    def __get__(self, instance, owner=None):
        if self.val is not None:
            return self.val
        if instance is not None and getattr(instance, "_secret_key_override", None) is not None:
            return instance._secret_key_override
        return self.default_factory()

    def __set__(self, instance, value):
        if instance is None:
            self.val = value
        else:
            instance._secret_key_override = value

def Field(default=None, default_factory=None, **kwargs):
    """Field helper for settings configuration."""
    if default_factory is not None:
        return _SecretKeyDescriptor(default_factory)
    return default

class Settings:
    PROJECT_NAME: str = "Issue-to-PR Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Security: configurable via environment
    SECRET_KEY: str = Field(default_factory=lambda: os.getenv("SECRET_KEY", "issuetopr_secure_jwt_secret_mwps_2026"))
    
    # Database
    DATABASE_URL: str = Field(default_factory=_normalize_database_url)
    SQLITE_FALLBACK_URL: str = f"sqlite+aiosqlite:///{DEFAULT_DATA_DIR}/issuetopr.db"
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # GitHub Integration
    GITHUB_TOKEN: Optional[str] = _get_github_token()
    GITHUB_API_BASE: str = "https://api.github.com"
    GITHUB_API_VERSION: str = "2022-11-28"
    GITHUB_CLIENT_ID: Optional[str] = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: Optional[str] = os.getenv("GITHUB_CLIENT_SECRET", "")
    GITHUB_REDIRECT_URI: str = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:8000/api/v1/auth/github/callback")
    GITHUB_WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "test_github_webhook_secret_hmac_2026")
    FRONTEND_AUTH_CALLBACK_URL: str = os.getenv("FRONTEND_AUTH_CALLBACK_URL", "http://localhost:5173/auth/callback")

    # Google OAuth Integration
    GOOGLE_CLIENT_ID: Optional[str] = os.getenv(
        "GOOGLE_CLIENT_ID",
        "842489213804-lnvakm6obbd26vj8qsdi8s3ri3fq1aev.apps.googleusercontent.com"
    )
    GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")

    # GitLab OAuth Integration
    GITLAB_CLIENT_ID: Optional[str] = os.getenv("GITLAB_CLIENT_ID", "")
    GITLAB_CLIENT_SECRET: Optional[str] = os.getenv("GITLAB_CLIENT_SECRET", "")
    GITLAB_REDIRECT_URI: str = os.getenv("GITLAB_REDIRECT_URI", "http://localhost:8000/api/v1/auth/gitlab/callback")

    # Stripe & Monetization Settings
    STRIPE_SECRET_KEY: Optional[str] = os.getenv("STRIPE_SECRET_KEY", "sk_test_mock_stripe_key_2026")
    STRIPE_PUBLISHABLE_KEY: Optional[str] = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_mock_stripe_key_2026")
    STRIPE_WEBHOOK_SECRET: Optional[str] = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_mock_stripe_webhook_secret_2026")
    STRIPE_PRO_MONTHLY_PRICE_ID: str = os.getenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_pro_monthly_29")
    STRIPE_PRO_ANNUAL_PRICE_ID: str = os.getenv("STRIPE_PRO_ANNUAL_PRICE_ID", "price_pro_annual_290")
    STRIPE_TEAM_SEAT_PRICE_ID: str = os.getenv("STRIPE_TEAM_SEAT_PRICE_ID", "price_team_monthly_79")
    BILLING_SUCCESS_URL: str = os.getenv("BILLING_SUCCESS_URL", "http://localhost:5173/?billing=success")
    BILLING_CANCEL_URL: str = os.getenv("BILLING_CANCEL_URL", "http://localhost:5173/?billing=cancel")
    FREE_TIER_MONTHLY_TASK_LIMIT: int = int(os.getenv("FREE_TIER_MONTHLY_TASK_LIMIT", "5"))
    
    # Workspace & Worktree
    DATA_DIR: Path = DEFAULT_DATA_DIR
    WORKSPACE_ROOT: Path = DEFAULT_WORKSPACE_DIR
    REPOS_CACHE_DIR: Path = DEFAULT_REPOS_CACHE_DIR
    WORKSPACE_PROVIDER: str = os.getenv("WORKSPACE_PROVIDER", "local")
    E2B_API_KEY: Optional[str] = os.getenv("E2B_API_KEY")

    # Distributed Task Queue & Messaging
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    POLAR_ACCESS_TOKEN: Optional[str] = os.getenv("POLAR_ACCESS_TOKEN")
    
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
