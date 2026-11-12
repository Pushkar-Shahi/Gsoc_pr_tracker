import json
import logging
import re
from typing import Optional, Dict, Any, List
import httpx

logger = logging.getLogger(__name__)


def _extract_json_block(raw_text: str) -> Optional[Dict[str, Any]]:
    """Extracts a JSON object from LLM text, stripping markdown code fences if present."""
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)
    else:
        brace_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if brace_match:
            cleaned = brace_match.group(1)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


class LLMService:
    """
    Unified BYOK LLM client supporting Google Gemini, OpenAI, Anthropic Claude,
    and OpenAI-compatible custom endpoints with safe fallback semantics.
    """

    @staticmethod
    async def generate_issue_brief(
        api_key: str,
        provider: str,
        owner: str,
        repo: str,
        issue_number: int,
        title: str,
        body: str,
        language: Optional[str] = None,
        custom_endpoint: Optional[str] = None,
        timeout_sec: float = 12.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Generates a structured engineering triage brief for a GitHub issue.
        Returns None cleanly on missing key, network error, or invalid JSON so callers
        can degrade to deterministic heuristic analysis without failing the request.
        """
        key = (api_key or "").strip()
        if not key:
            return None

        prov = (provider or "gemini").lower().strip()
        prompt = (
            f"You are a senior open-source engineer triaging GitHub issue #{issue_number} in {owner}/{repo}.\n"
            f"Language: {language or 'unknown'}\n"
            f"Title: {title}\n"
            f"Body:\n{(body or '')[:3500]}\n\n"
            "Respond strictly with valid JSON matching this schema:\n"
            "{\n"
            '  "executive_summary": "2-3 concise sentences summarizing the issue",\n'
            '  "root_cause_analysis": "likely root cause or design constraint",\n'
            '  "affected_files": ["relative/path/to/file.ext"],\n'
            '  "proposed_plan": ["Step 1...", "Step 2...", "Step 3...", "Step 4..."],\n'
            '  "test_command": "concise command to verify changes"\n'
            "}"
        )

        raw_response: Optional[str] = None
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            try:
                if prov == "gemini":
                    url = (
                        "https://generativelanguage.googleapis.com/v1beta/"
                        f"models/gemini-2.5-flash:generateContent?key={key}"
                    )
                    resp = await client.post(
                        url,
                        json={
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates") or []
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                raw_response = parts[0].get("text")

                elif prov == "anthropic":
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": "claude-3-5-sonnet-latest",
                            "max_tokens": 900,
                            "temperature": 0.2,
                            "messages": [{"role": "user", "content": prompt}],
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        content = data.get("content") or []
                        if content and isinstance(content, list):
                            raw_response = content[0].get("text")

                elif prov in ("openai", "custom"):
                    if prov == "custom" and custom_endpoint:
                        base = custom_endpoint.rstrip("/")
                        url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
                    else:
                        url = "https://api.openai.com/v1/chat/completions"
                    resp = await client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "gpt-4o-mini" if prov == "openai" else "default",
                            "temperature": 0.2,
                            "max_tokens": 900,
                            "messages": [
                                {"role": "system", "content": "Return valid JSON only."},
                                {"role": "user", "content": prompt},
                            ],
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices") or []
                        if choices:
                            raw_response = choices[0].get("message", {}).get("content")
            except Exception as exc:
                logger.warning(f"BYOK LLM call ({prov}) failed, falling back to heuristic brief: {exc}")
                return None

        parsed = _extract_json_block(raw_response or "")
        if not parsed:
            return None

        plan_items: List[str] = []
        if isinstance(parsed.get("proposed_plan"), list):
            plan_items = [str(step).strip() for step in parsed["proposed_plan"] if str(step).strip()][:8]

        files_items: List[str] = []
        if isinstance(parsed.get("affected_files"), list):
            files_items = [str(f).strip() for f in parsed["affected_files"] if str(f).strip()][:8]

        return {
            "executive_summary": str(parsed.get("executive_summary") or "").strip() or None,
            "root_cause_analysis": str(parsed.get("root_cause_analysis") or "").strip() or None,
            "affected_files": files_items or None,
            "proposed_plan": plan_items or None,
            "test_command": str(parsed.get("test_command") or "").strip() or None,
        }

