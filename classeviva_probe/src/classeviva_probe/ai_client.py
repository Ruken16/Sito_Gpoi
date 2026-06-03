from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


class AIConfigurationError(RuntimeError):
    pass


class AIProviderError(RuntimeError):
    pass


@dataclass
class AIConfig:
    provider: str
    api_key: str | None
    model: str
    timeout_seconds: int = 45

    @property
    def enabled(self) -> bool:
        return self.provider == "gemini" and bool(self.api_key)

    @property
    def label(self) -> str:
        if self.provider == "gemini":
            return f"Gemini · {self.model}"
        return self.provider


def load_ai_config(*, dotenv_path: str | os.PathLike[str] | None = None) -> AIConfig:
    if dotenv_path:
        load_dotenv(dotenv_path=Path(dotenv_path))
    else:
        load_dotenv()

    provider = (os.getenv("AI_PROVIDER") or "gemini").strip().lower()
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip() or None
    model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    timeout_raw = (os.getenv("GEMINI_TIMEOUT_SECONDS") or "45").strip()
    try:
        timeout_seconds = max(10, int(timeout_raw))
    except ValueError:
        timeout_seconds = 45

    return AIConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )


def gemini_generate_reply(
    *,
    config: AIConfig,
    system_instruction: str,
    history: list[dict[str, Any]],
) -> str:
    if not config.api_key:
        raise AIConfigurationError(
            "Chat AI non configurata: aggiungi GEMINI_API_KEY al file .env per attivare il tutor con intelligenza artificiale reale."
        )

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:generateContent"
    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": system_instruction,
                }
            ]
        },
        "contents": history,
        "generationConfig": {
            "temperature": 0.45,
            "topP": 0.92,
            "maxOutputTokens": 900,
        },
    }
    response = requests.post(
        endpoint,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": config.api_key,
        },
        data=json.dumps(payload),
        timeout=config.timeout_seconds,
    )

    if response.status_code != 200:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise AIProviderError(f"Gemini ha rifiutato la richiesta: {detail}")

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise AIProviderError("Gemini non ha restituito alcuna risposta utilizzabile.")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "").strip() for part in parts if isinstance(part, dict) and part.get("text"))
    if not text:
        raise AIProviderError("Gemini ha restituito una risposta vuota.")
    return text.strip()
