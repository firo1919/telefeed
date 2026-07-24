"""
Configuration & XDG Path Resolution for TeleFeed.

Resolves paths according to the XDG Base Directory specification:
  Config  : ~/.config/telefeed/config.yaml
  Database: ~/.local/state/telefeed/telefeed.db
  Session : ~/.config/telefeed/telefeed.session

All credentials and options live inside config.yaml (no separate .env file).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


import platformdirs

def _get_xdg_dir(env_var: str, fallback_func) -> Path:
    val = os.getenv(env_var)
    if val:
        return Path(val) / "telefeed"
    return Path(fallback_func("telefeed"))

DEFAULT_CONFIG_DIR = _get_xdg_dir("XDG_CONFIG_HOME", platformdirs.user_config_dir)
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"

DEFAULT_STATE_DIR = _get_xdg_dir("XDG_STATE_HOME", platformdirs.user_state_dir)
DEFAULT_DB_PATH = DEFAULT_STATE_DIR / "telefeed.db"

DEFAULT_CACHE_DIR = _get_xdg_dir("XDG_CACHE_HOME", platformdirs.user_cache_dir)
DEFAULT_SESSION_FILE = DEFAULT_CONFIG_DIR / "telefeed.session"


@dataclass
class TelegramConfig:
    api_id: int = 0
    api_hash: str = ""
    phone: str = ""


@dataclass
class AIConfig:
    provider: str = "gemini"  # gemini | openai | anthropic | ollama | openrouter
    model: str = "gemini-2.5-flash"
    api_key: str = ""
    base_url: str = ""  # Optional: override endpoint (e.g. Ollama's local URL)


@dataclass
class TelegramBotNotifyConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class NotificationConfig:
    desktop: bool = True
    telegram_bot: TelegramBotNotifyConfig = field(default_factory=TelegramBotNotifyConfig)


@dataclass
class TeleFeedConfig:
    matcher: str = "keywords"
    threshold: int = 65
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    areas: list[dict[str, Any]] = field(default_factory=list)

    config_path: Path = DEFAULT_CONFIG_PATH
    db_path: Path = DEFAULT_DB_PATH
    session_path: Path = DEFAULT_SESSION_FILE

    @property
    def ai_threshold(self) -> int:
        return self.threshold


def get_config_path(custom_path: Optional[str] = None) -> Path:
    """Resolve config.yaml path using flag -> env -> ./ -> XDG fallback."""
    if custom_path:
        return Path(custom_path).expanduser().resolve()
    
    env_path = os.getenv("CONFIG_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    
    cwd_config = Path.cwd() / "config.yaml"
    if cwd_config.exists():
        return cwd_config
    
    return DEFAULT_CONFIG_PATH


def get_db_path() -> Path:
    """Resolve db path (env -> ./ -> XDG)."""
    env_db = os.getenv("DB_PATH")
    if env_db:
        return Path(env_db).expanduser().resolve()
    
    cwd_db = Path.cwd() / "telefeed.db"
    if cwd_db.exists():
        return cwd_db
    
    DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DB_PATH


def get_session_path() -> Path:
    """Resolve session path (env -> ./ -> XDG)."""
    env_session = os.getenv("SESSION_FILE")
    if env_session:
        return Path(env_session).expanduser().resolve()
    
    cwd_session = Path.cwd() / "telefeed.session"
    if cwd_session.exists():
        return cwd_session
    
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_SESSION_FILE


def load_telefeed_config(custom_path: Optional[str] = None) -> TeleFeedConfig:
    """Load and parse config.yaml into a structured TeleFeedConfig object."""
    config_path = get_config_path(custom_path)
    if not config_path.exists():
        # Return default config with resolved paths
        return TeleFeedConfig(
            config_path=config_path,
            db_path=get_db_path(),
            session_path=get_session_path(),
        )

    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    tg_raw = data.get("telegram", {})
    # Fallback to env vars for backward compatibility
    api_id = int(tg_raw.get("api_id") or os.getenv("TELEGRAM_API_ID") or 0)
    api_hash = str(tg_raw.get("api_hash") or os.getenv("TELEGRAM_API_HASH") or "")
    phone = str(tg_raw.get("phone") or os.getenv("TELEGRAM_PHONE") or "")

    # New unified ai: section; fall back to legacy gemini: section for compatibility
    ai_raw = data.get("ai") or data.get("gemini", {})
    ai_provider = str(ai_raw.get("provider", "gemini")).lower().strip()
    ai_model = str(ai_raw.get("model", "")).strip()
    ai_key = str(ai_raw.get("api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY") or "")
    ai_base_url = str(ai_raw.get("base_url", "")).strip()

    # Provide sensible default models per provider if not specified
    if not ai_model:
        ai_model = {
            "gemini": "gemini-2.5-flash",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-20241022",
            "ollama": "llama3.2",
            "openrouter": "meta-llama/llama-3.1-8b-instruct",
        }.get(ai_provider, "gemini-2.5-flash")

    notif_raw = data.get("notifications", {})
    desktop_enabled = bool(notif_raw.get("desktop", True))

    bot_raw = notif_raw.get("telegram_bot", {})
    bot_enabled = bool(bot_raw.get("enabled", False))
    bot_token = str(bot_raw.get("bot_token", ""))
    chat_id = str(bot_raw.get("chat_id", ""))

    matcher = str(data.get("matcher", "keywords")).lower().strip()
    if matcher not in ("keywords", "ai"):
        matcher = "keywords"

    threshold = int(data.get("threshold", data.get("ai_threshold", 65)))
    threshold = max(0, min(100, threshold))

    return TeleFeedConfig(
        matcher=matcher,
        threshold=threshold,
        telegram=TelegramConfig(api_id=api_id, api_hash=api_hash, phone=phone),
        ai=AIConfig(provider=ai_provider, model=ai_model, api_key=ai_key, base_url=ai_base_url),
        notifications=NotificationConfig(
            desktop=desktop_enabled,
            telegram_bot=TelegramBotNotifyConfig(
                enabled=bot_enabled,
                bot_token=bot_token,
                chat_id=chat_id,
            ),
        ),
        areas=data.get("areas", []),
        config_path=config_path,
        db_path=get_db_path(),
        session_path=get_session_path(),
    )


CONFIG_TEMPLATE = """# TeleFeed Configuration
# Define credentials, notification settings, and areas of concern.

matcher: keywords        # 'keywords' or 'ai'
threshold: 65            # Minimum relevance score threshold (0-100) for both keyword & AI modes

telegram:
  api_id: YOUR_TELEGRAM_API_ID
  api_hash: "YOUR_TELEGRAM_API_HASH"
  phone: "+YOUR_PHONE_NUMBER"

# AI provider configuration
# Supported providers: gemini | openai | anthropic | ollama | openrouter
ai:
  provider: gemini
  model: gemini-2.5-flash     # Leave blank to auto-select default model per provider
  api_key: "YOUR_API_KEY"     # Not needed for Ollama (local)
  base_url: ""                # Override endpoint e.g. http://localhost:11434/v1 for Ollama

notifications:
  desktop: true          # Send OS desktop popup notifications
  telegram_bot:
    enabled: false       # Set to true to push matched posts to your Telegram chat
    bot_token: ""        # From @BotFather
    chat_id: ""          # Your personal Telegram user ID or chat ID

areas:
  - name: "Remote Software Jobs"
    description: >
      Job postings for software developers or engineers. Preferably remote
      positions. Interested in backend, full-stack, Python, Rust, or Go roles.
      Not interested in internships, unpaid positions, or on-site only roles.
    keywords:
      - software engineer
      - software developer
      - backend developer
      - full stack
      - python developer
      - remote
      - hiring
      - job opening
    negative_keywords:
      - internship
      - unpaid
      - volunteer

  - name: "AI & Machine Learning News"
    description: >
      News, papers, tools, or discussions about large language models,
      generative AI, AI agents, or machine learning research.
    keywords:
      - llm
      - large language model
      - generative ai
      - gpt
      - transformer
      - ai agent
    negative_keywords: []
"""
