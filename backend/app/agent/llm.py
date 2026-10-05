"""Optional LLM narration.

The LLM is a *writer*, not a source of truth. It receives a compact fact sheet
already retrieved from FalkorDB and is instructed to explain only those facts.
When no key is configured -- or anything fails -- NEXUS falls back to a
deterministic template. The mode is always reported to the client.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings

SYSTEM_PROMPT = (
    "You are NEXUS, an incident-commander assistant. You are given FACTS that were "
    "retrieved from a graph database. Explain them clearly and concisely. "
    "RULES: never invent entities, numbers, incidents or relationships; use only the "
    "provided facts; if the facts are insufficient say so. Reply in 2-5 sentences."
)


class LLMClient:
    def __init__(self) -> None:
        self.provider = settings.llm_provider
        self.model = settings.llm_model
        self.key = settings.llm_api_key
        self.base_url = settings.llm_base_url

    @property
    def available(self) -> bool:
        return bool(self.key)

    def narrate(self, question: str, facts: dict[str, Any], fallback: str) -> tuple[str, bool]:
        """Return (text, used_llm). Never raises."""
        if not self.available:
            return fallback, False
        try:
            prompt = (
                f"QUESTION: {question}\n\n"
                f"FACTS (JSON, the only permitted source):\n"
                f"{json.dumps(facts, default=str)[:6000]}\n\n"
                f"Draft the answer using only these facts."
            )
            text = self._call(prompt)
            if text:
                return text.strip(), True
        except Exception:
            pass
        return fallback, False

    def _call(self, prompt: str) -> str | None:
        with httpx.Client(timeout=30.0) as client:
            if self.provider == "anthropic":
                r = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 500,
                        "system": SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                r.raise_for_status()
                data = r.json()
                return "".join(
                    block.get("text", "") for block in data.get("content", [])
                ) or None

            if self.provider in ("gemini", "google"):
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{self.model}:generateContent?key={self.key}"
                )
                r = client.post(url, json={
                    "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "contents": [{"parts": [{"text": prompt}]}],
                })
                r.raise_for_status()
                data = r.json()
                cands = data.get("candidates") or []
                if not cands:
                    return None
                parts = cands[0].get("content", {}).get("parts", [])
                return "".join(p.get("text", "") for p in parts) or None

            # OpenAI and any OpenAI-compatible endpoint (Groq, Together, Ollama...)
            base = (self.base_url or "https://api.openai.com/v1").rstrip("/")
            r = client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {self.key}",
                         "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"] or None


llm = LLMClient()
