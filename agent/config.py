"""Central configuration: every tunable comes from the environment.

Load order: `load_dotenv()` must run first (cli.py and ui/server.py do this),
then `get_settings()` reads everything from `os.environ` exactly once.
Nothing in the codebase reads env vars ad-hoc — add new tunables here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Supported LLM providers. All expose an OpenAI-compatible chat-completions
# API, so the same `openai` SDK client works for all three -- `LLM_PROVIDER`
# just picks the default base URL and default model; the key always comes
# from the single generic `LLM_API_KEY` variable.
PROVIDERS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4o-mini",
    },
    "ollama": {
        # Ollama CLOUD -- the hosted service at ollama.com, NOT a local
        # Ollama daemon. Do NOT "fix" this to localhost:11434; the cloud
        # API is OpenAI-compatible and needs an LLM_API_KEY.
        "base_url": "https://ollama.com/v1",
        "default_model": "qwen3:8b",
    },
}

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    # LLM
    llm_provider: str
    api_key: Optional[str]
    base_url: str
    model: str
    openrouter_referer: str
    openrouter_title: str
    # agent loop
    max_steps: int
    token_budget: int
    llm_timeout: float
    # paths
    workspace_dir: Path
    workspace_original_dir: Path
    # web server (bare-metal `python ui/server.py`; compose maps its own port)
    host: str
    port: int


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}")


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}")


def load_settings() -> Settings:
    provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower() or "openai"
    if provider not in PROVIDERS:
        raise ValueError(
            f"LLM_PROVIDER must be one of {sorted(PROVIDERS)}, got {provider!r}"
        )
    spec = PROVIDERS[provider]

    # One generic key variable for whichever provider was picked.
    api_key = os.environ.get("LLM_API_KEY") or None

    # Base URL / model: generic override, else the provider's default.
    base_url = os.environ.get("LLM_BASE_URL") or spec["base_url"]
    model = os.environ.get("LLM_MODEL") or spec["default_model"]

    return Settings(
        llm_provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        openrouter_referer=os.environ.get(
            "OPENROUTER_REFERER", "https://github.com/ai-file-agent"
        ),
        openrouter_title=os.environ.get("OPENROUTER_TITLE", "AI File Agent"),
        max_steps=_int_env("MAX_STEPS", 15),
        token_budget=_int_env("TOKEN_BUDGET", 200_000),
        llm_timeout=_float_env("LLM_TIMEOUT", 120.0),
        workspace_dir=Path(
            os.environ.get("WORKSPACE_DIR", str(REPO_ROOT / "workspace"))
        ).resolve(),
        workspace_original_dir=Path(
            os.environ.get("WORKSPACE_ORIGINAL_DIR", str(REPO_ROOT / "workspace_original"))
        ).resolve(),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=_int_env("PORT", 8000),
    )


_cache: Optional[Settings] = None


def get_settings() -> Settings:
    """Process-wide settings, resolved once. Call load_dotenv() first."""
    global _cache
    if _cache is None:
        _cache = load_settings()
    return _cache


def reset_settings_cache() -> None:
    """For tests: drop the cached settings so env changes are re-read."""
    global _cache
    _cache = None
