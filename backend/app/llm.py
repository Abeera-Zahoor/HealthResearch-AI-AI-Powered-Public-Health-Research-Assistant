"""A small, provider-agnostic LLM client (OpenAI-compatible APIs and Anthropic).

It uses plain HTTPS calls (no vendor SDKs), reads its settings from backend/.env and
never logs or returns the API key.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Optional

import httpx

from .config import Settings
from .schemas import LLMInfo

RETRY_STATUS = {429, 500, 502, 503, 504}
OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
ANTHROPIC_DEFAULT_BASE = "https://api.anthropic.com"


class LLMError(Exception):
    """The LLM could not be used (not configured, request failed, or unusable answer)."""


def extract_json(text: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences and surrounding prose."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()
    candidates = [cleaned]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        candidates.append(cleaned[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise LLMError("The model did not return valid JSON.")


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        http: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._http = http
        self._sleep = sleep

    @property
    def enabled(self) -> bool:
        return self.settings.llm_enabled

    @property
    def info(self) -> LLMInfo:
        s = self.settings
        return LLMInfo(enabled=self.enabled, provider=s.llm_provider, model=s.resolved_model if self.enabled else "")

    # ------------------------------------------------------------------
    def complete(self, system: str, user: str, *, json_mode: bool = False, max_tokens: Optional[int] = None) -> str:
        if not self.enabled:
            raise LLMError(self.settings.llm_problem or "No LLM is configured (LLM_PROVIDER=none).")
        max_tokens = max_tokens or self.settings.llm_max_tokens
        if self.settings.llm_provider == "anthropic":
            url, headers, payload = self._anthropic_request(system, user, max_tokens)
        else:
            url, headers, payload = self._openai_request(system, user, max_tokens, json_mode)
        data = self._post(url, headers, payload)
        return self._read_text(data)

    def complete_json(self, system: str, user: str, *, max_tokens: Optional[int] = None) -> dict:
        text = self.complete(system, user, json_mode=True, max_tokens=max_tokens)
        try:
            return extract_json(text)
        except LLMError:
            retry = self.complete(
                system,
                user + "\n\nYour previous answer was not valid JSON. Reply with ONE valid JSON object only.",
                json_mode=True,
                max_tokens=max_tokens,
            )
            try:
                return extract_json(retry)
            except LLMError as exc:
                raise LLMError(
                    "The model did not return valid JSON (the answer may have been cut off; "
                    "try raising LLM_MAX_TOKENS in backend/.env)."
                ) from exc

    # ------------------------------------------------------------------
    def _openai_request(self, system: str, user: str, max_tokens: int, json_mode: bool):
        s = self.settings
        official = not s.llm_base_url.strip()
        base = (s.llm_base_url.strip() or OPENAI_DEFAULT_BASE).rstrip("/")
        headers = {"Content-Type": "application/json"}
        if s.llm_api_key.strip():
            headers["Authorization"] = f"Bearer {s.llm_api_key.strip()}"
        payload: dict[str, Any] = {
            "model": s.resolved_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if official:
            # Newer OpenAI models use max_completion_tokens and only support default temperature.
            payload["max_completion_tokens"] = max_tokens
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
        else:
            payload["max_tokens"] = max_tokens
            payload["temperature"] = 0.2
        return f"{base}/chat/completions", headers, payload

    def _anthropic_request(self, system: str, user: str, max_tokens: int):
        s = self.settings
        base = (s.llm_base_url.strip() or ANTHROPIC_DEFAULT_BASE).rstrip("/")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": s.llm_api_key.strip(),
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": s.resolved_model,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        return f"{base}/v1/messages", headers, payload

    def _post(self, url: str, headers: dict, payload: dict) -> dict:
        timeout = self.settings.llm_timeout_seconds
        last = "unknown error"
        for attempt in range(3):
            try:
                if self._http is not None:
                    response = self._http.post(url, headers=headers, json=payload, timeout=timeout)
                else:
                    with httpx.Client(timeout=timeout) as client:
                        response = client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                last = f"network error ({type(exc).__name__})"
            else:
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise LLMError("The LLM provider returned a response that is not JSON.") from exc
                last = f"HTTP {response.status_code}: {self._error_message(response)}"
                if response.status_code not in RETRY_STATUS:
                    break
            if attempt < 2:
                self._sleep(2 * (attempt + 1))
        raise LLMError(f"LLM request failed ({last}). Check LLM_PROVIDER, LLM_API_KEY and LLM_MODEL in backend/.env.")

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
            error = body.get("error", body) if isinstance(body, dict) else body
            message = error.get("message") if isinstance(error, dict) else str(error)
        except ValueError:
            message = response.text
        return " ".join(str(message or "").split())[:300]

    def _read_text(self, data: dict) -> str:
        try:
            if self.settings.llm_provider == "anthropic":
                text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
            else:
                text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("The LLM provider returned an unexpected response format.") from exc
        if not text.strip():
            raise LLMError("The LLM returned an empty answer.")
        return text
