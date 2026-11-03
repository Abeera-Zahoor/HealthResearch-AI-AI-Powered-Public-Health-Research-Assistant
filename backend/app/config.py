"""Application settings, loaded from backend/.env and environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

SUPPORTED_PROVIDERS = ("openai", "anthropic")
DEFAULT_MODELS = {"openai": "gpt-4o-mini", "anthropic": "claude-haiku-5-5"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: str = "none"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    llm_timeout_seconds: float = 120.0
    llm_max_tokens: int = 3500

    # Literature APIs
    ncbi_api_key: str = ""
    ncbi_email: str = ""
    include_preprints: bool = False
    http_timeout_seconds: float = 25.0
    pubmed_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    europepmc_base_url: str = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    # App
    default_max_papers: int = 10
    database_path: str = str(BACKEND_DIR / "data" / "healthresearch.db")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, value: object) -> str:
        text = str(value or "none").strip().lower()
        return "none" if text in ("", "off", "disabled", "false", "no") else text

    # ---- derived helpers -------------------------------------------------
    @property
    def resolved_model(self) -> str:
        return self.llm_model.strip() or DEFAULT_MODELS.get(self.llm_provider, "")

    @property
    def llm_problem(self) -> Optional[str]:
        """Human-readable reason the LLM cannot be used (None if fine or intentionally off)."""
        provider = self.llm_provider
        if provider == "none":
            return None
        if provider not in SUPPORTED_PROVIDERS:
            return f"LLM_PROVIDER '{provider}' is not supported. Use openai, anthropic or none."
        has_key = bool(self.llm_api_key.strip())
        if provider == "anthropic" and not has_key:
            return "LLM_PROVIDER is anthropic but LLM_API_KEY is empty."
        if provider == "openai" and not has_key and not self.llm_base_url.strip():
            return "LLM_PROVIDER is openai but LLM_API_KEY is empty."
        if not self.resolved_model:
            return "LLM_MODEL is required for this provider."
        return None

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider in SUPPORTED_PROVIDERS and self.llm_problem is None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
