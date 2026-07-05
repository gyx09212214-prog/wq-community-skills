from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any

from .io_utils import stable_hash


@dataclass(frozen=True)
class LLMAudit:
    enabled: bool
    provider: str
    model: str
    prompt_hash: str
    allow_raw_llm: bool
    redacted_only: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "prompt_hash": self.prompt_hash,
            "allow_raw_llm": self.allow_raw_llm,
            "redacted_only": self.redacted_only,
        }


def build_llm_audit(evidence: list[dict[str, Any]], *, model: str = "", allow_raw_llm: bool = False) -> LLMAudit:
    resolved_model = model or os.environ.get("WQ_SKILL_MODEL", "deterministic-rules")
    prompt = {
        "task": "cluster redacted community evidence into template and repair skill drafts",
        "evidence_count": len(evidence),
        "evidence_hash": stable_hash(evidence),
        "raw_allowed": allow_raw_llm,
    }
    return LLMAudit(
        enabled=bool(os.environ.get("OPENAI_API_KEY")) and resolved_model != "deterministic-rules",
        provider="openai-compatible",
        model=resolved_model,
        prompt_hash=stable_hash(prompt),
        allow_raw_llm=allow_raw_llm,
        redacted_only=not allow_raw_llm,
    )


def openai_compatible_chat(prompt: str, *, model: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data["choices"][0]["message"]["content"])
