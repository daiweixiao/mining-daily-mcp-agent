from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from project_env import load_dotenv


def llm_enabled() -> bool:
    load_dotenv()
    return _truthy(os.getenv("LLM_ENABLED")) and bool(os.getenv("OPENAI_API_KEY"))


def enhance_report(base_report: str, evidence: dict[str, Any]) -> str:
    """Use an OpenAI-compatible chat model to polish the report, with safe fallback."""

    if not llm_enabled():
        return base_report

    try:
        polished = _chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a mining analyst. Rewrite the provided Markdown daily report "
                        "in clear professional Chinese. Preserve all numeric facts, source links, "
                        "section headings, and citations. Do not add unsupported claims. If evidence "
                        "is weak, state that explicitly."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "base_report": base_report,
                            "evidence": evidence,
                        },
                        ensure_ascii=False,
                    ),
                },
            ]
        )
    except Exception as exc:  # noqa: BLE001 - report generation must degrade safely
        return base_report + f"\n\n> LLM 增强失败，已回退到规则版：{exc}\n"

    if not polished.strip() or "##" not in polished:
        return base_report + "\n\n> LLM 增强结果不完整，已回退到规则版。\n"
    return polished.strip() + "\n"


def _chat_completion(messages: list[dict[str, str]]) -> str:
    api_key = os.environ["OPENAI_API_KEY"]
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1800"))
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {exc.code}: {detail[:500]}") from exc

    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM response has no choices: {raw[:500]}")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"LLM response has no message content: {raw[:500]}")
    return content


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}

