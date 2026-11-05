import pytest
import tempfile
import asyncio
from pathlib import Path
from app.services.validation_service import ValidationService

@pytest.mark.asyncio
async def test_secret_scanner_detects_rsa_and_tokens(tmp_path):
    val = ValidationService()

    # Initialize a temporary git repository
    proc = await asyncio.create_subprocess_exec("git", "init", cwd=str(tmp_path))
    await proc.communicate()
    proc = await asyncio.create_subprocess_exec("git", "config", "user.name", "CI Bot", cwd=str(tmp_path))
    await proc.communicate()
    proc = await asyncio.create_subprocess_exec("git", "config", "user.email", "ci@example.com", cwd=str(tmp_path))
    await proc.communicate()

    # Commit initial file
    initial_file = tmp_path / "main.py"
    initial_file.write_text("print('hello')", encoding="utf-8")
    proc = await asyncio.create_subprocess_exec("git", "add", "main.py", cwd=str(tmp_path))
    await proc.communicate()
    proc = await asyncio.create_subprocess_exec("git", "commit", "-m", "init", cwd=str(tmp_path))
    await proc.communicate()

    # Now create an unstaged file with a simulated leaked token
    secret_file = tmp_path / "config.py"
    secret_file.write_text("API_KEY = 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'", encoding="utf-8")
    proc = await asyncio.create_subprocess_exec("git", "add", "config.py", cwd=str(tmp_path))
    await proc.communicate()

    report = await val.scan_git_diff(str(tmp_path))
    assert report["passed"] is False
    assert any("GitHub Personal Access Token" in s for s in report["secrets_detected"])

@pytest.mark.asyncio
async def test_detects_prohibited_env_file(tmp_path):
    val = ValidationService()

    proc = await asyncio.create_subprocess_exec("git", "init", cwd=str(tmp_path))
    await proc.communicate()

    # Add .env file
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=12345", encoding="utf-8")

    report = await val.scan_git_diff(str(tmp_path))
    assert report["passed"] is False
    assert any(".env" in f for f in report["unrelated_files"])
