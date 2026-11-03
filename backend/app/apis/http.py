"""Shared HTTP helpers: one client, retries with back-off, and safe error messages."""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Optional

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}
USER_AGENT = "HealthResearchAI/1.0 (open-source portfolio project)"


class SourceError(Exception):
    """A literature API could not be reached or returned an unusable answer."""


def build_http_client(timeout: float = 25.0) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(timeout),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def scrub(text: str) -> str:
    """Remove anything that looks like an API key from a message before it is shown."""
    return re.sub(r"(api_key=)[^&\s'\"]+", r"\1***", text)


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: Optional[dict[str, Any]],
    source: str,
    retries: int = 2,
    backoff: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET with retry on network errors, HTTP 429 and 5xx. Raises SourceError when it gives up."""
    last = "unknown error"
    for attempt in range(retries + 1):
        try:
            response = client.get(url, params=params)
        except httpx.HTTPError as exc:
            last = scrub(f"{type(exc).__name__}: {exc}".strip(": "))
        else:
            if response.status_code < 400:
                return response
            last = f"HTTP {response.status_code}"
            if response.status_code not in RETRY_STATUS:
                break
        if attempt < retries:
            sleep(backoff * (2**attempt))
    raise SourceError(f"{source} request failed ({last}).")
