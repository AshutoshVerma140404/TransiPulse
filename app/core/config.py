"""Application configuration loaded from environment variables / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for TransiPulse.

    All values can be overridden via environment variables or a `.env` file.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TRANSIPULSE_", extra="ignore")

    # ---- Application ----
    app_name: str = "TransiPulse"
    app_version: str = "0.1.0"
    app_description: str = (
        "Public Transport Feedback & Service Analytics Platform — "
        "commuter feedback portal and intelligent operations analytics."
    )
    debug: bool = False

    # ---- Server ----
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True

    # ---- Database ----
    database_url: str = "sqlite+aiosqlite:///./transipulse.db"
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # ---- Analytics ----
    bayesian_m: int = 15
    bayesian_confidence: float = 0.95
    deterioration_velocity_threshold: float = -0.3
    deterioration_complaint_accel_threshold: float = 0.2
    deterioration_alpha: float = 0.6
    deterioration_beta: float = 0.4
    short_window_days: int = 7
    long_window_days: int = 30
    worst_period_window_hours: int = 2

    # ---- AI ----
    ai_provider: str = "ollama"  # ollama | transformers | heuristic
    ai_model: str = "gemma4:31b-cloud"        # Installed Ollama model
    gemini_model: str = "gemini-2.0-flash-lite"  # Google Gemini fallback model
    ai_max_tokens: int = 256
    ai_temperature: float = 0.0
    ai_timeout_seconds: float = 15.0
    ai_enabled: bool = True
    ai_fallback_enabled: bool = True
    ollama_host: str = "http://localhost:11434"  # Ollama REST base URL

    # ---- Security ----
    api_key: str = "transipulse-dev-key"
    cors_origins: list[str] = ["*"]

    # ---- Data ----
    mta_sample_size: int = 5000
    seed_data_enabled: bool = True


settings = Settings()