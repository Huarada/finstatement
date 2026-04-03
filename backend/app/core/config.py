"""
Application configuration.

All config is loaded from environment variables with sane defaults.
No secrets are hard-coded.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from the environment."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # AI — max_tokens raised to 4096 for the richer analysis prompt
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-20250514"
    ai_max_tokens: int = 4096

    # PDF processing
    max_pdf_size_mb: int = 50
    max_pages_for_meta: int = 3

    # Scoring
    bank_sector_patterns: tuple[str, ...] = field(default_factory=lambda: (
        "banco", "itaú", "bradesco", "santander", "btg", "caixa econômica",
        "nubank", "xp", "c6 bank", "sicoob", "sicredi", "inter bank",
    ))

    @classmethod
    def from_env(cls) -> "Settings":
        """Factory — reads from os.environ with type coercion."""
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            debug=os.getenv("DEBUG", "false").lower() == "true",
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            ai_model=os.getenv("AI_MODEL", "claude-sonnet-4-20250514"),
            ai_max_tokens=int(os.getenv("AI_MAX_TOKENS", "4096")),
            max_pdf_size_mb=int(os.getenv("MAX_PDF_SIZE_MB", "50")),
        )


# Module-level singleton
settings = Settings.from_env()

