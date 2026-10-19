"""
config.py
=========
Centralised, environment-driven configuration for the backend.

All secrets and endpoints are pulled from the local environment (`.env`)
via `python-dotenv` / `pydantic-settings`. Nothing is hardcoded here, in
line with the frozen system-design security constraints.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from `.env`."""

    # --- MongoDB (Motor / async) -----------------------------------------
    mongo_uri: str = Field(..., alias="MONGO_URI")
    mongo_db_name: str = Field("feedback_analysis_db", alias="MONGO_DB_NAME")
    mongo_timeout_ms: int = Field(5000, alias="MONGO_TIMEOUT_MS")

    # --- Gemini 1.5 Flash (Tier D) ---------------------------------------
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-3.6-flash", alias="GEMINI_MODEL")

    # --- DistilBERT (Tier B) ---------------------------------------------
    sentiment_model: str = Field(
        "distilbert-base-uncased-finetuned-sst-2-english",
        alias="SENTIMENT_MODEL",
    )
    neutral_threshold: float = Field(0.60, alias="NEUTRAL_THRESHOLD")

    # --- Tier B → Gemini sentiment fallback ------------------------------
    # DistilBERT is trained on English movie reviews and mislabels sarcasm and
    # Nigerian Pidgin/slang (often with high confidence). When enabled, such
    # cases are escalated to Gemini for a second opinion that overrides Tier B.
    gemini_sentiment_fallback: bool = Field(True, alias="GEMINI_SENTIMENT_FALLBACK")
    sentiment_escalate_threshold: float = Field(0.75, alias="SENTIMENT_ESCALATE_THRESHOLD")
    # Hard cap on the escalation call so a slow/rate-limited Gemini (the SDK
    # retries 429s with backoff and can hang ~90s) never stalls a submission —
    # on timeout we fall back to the DistilBERT label immediately.
    gemini_timeout_seconds: float = Field(8.0, alias="GEMINI_TIMEOUT_SECONDS")

    # --- spaCy (Tier A) --------------------------------------------------
    spacy_model: str = Field("en_core_web_sm", alias="SPACY_MODEL")

    # --- Administrator authentication (JWT) ------------------------------
    jwt_secret_key: str = Field("change-me-in-production", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(480, alias="JWT_EXPIRE_MINUTES")

    # --- CORS ------------------------------------------------------------
    cors_origins: str = Field(
        "http://localhost:5173,http://localhost:8501", alias="CORS_ORIGINS"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        """Parse the comma-separated CORS origins into a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton (avoids re-parsing `.env`)."""
    return Settings()
