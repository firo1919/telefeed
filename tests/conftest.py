"""
Global pytest configuration and shared fixtures for TeleFeed.
"""

from pathlib import Path
import tempfile
import pytest

from telefeed.config import TeleFeedConfig, TelegramConfig, GeminiConfig, NotificationConfig, TelegramBotNotifyConfig
from telefeed.filters import Area


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory Path for tests."""
    return tmp_path


@pytest.fixture
def sample_config_yaml(tmp_path: Path) -> Path:
    """Create a sample valid config.yaml in a temporary directory."""
    config_file = tmp_path / "config.yaml"
    content = """
matcher: ai
ai_threshold: 70

telegram:
  api_id: 11111111
  api_hash: "test_api_hash"
  phone: "+15551234567"

gemini:
  api_key: "test_gemini_key"

notifications:
  desktop: true
  telegram_bot:
    enabled: true
    bot_token: "123456:test_bot_token"
    chat_id: "987654321"

areas:
  - name: "Python Dev"
    description: "Backend Python developer positions."
    keywords:
      - python
      - fastapi
      - django
    negative_keywords:
      - unpaid
      - intern
    sources:
      - "pyjobs"

  - name: "AI News"
    description: "Latest news on LLMs and AI models."
    keywords:
      - llm
      - gemini
      - gpt
    negative_keywords: []
"""
    config_file.write_text(content, encoding="utf-8")
    return config_file


@pytest.fixture
def sample_telefeed_config(sample_config_yaml: Path, tmp_path: Path) -> TeleFeedConfig:
    """Return a TeleFeedConfig object with resolved temporary paths."""
    return TeleFeedConfig(
        matcher="ai",
        ai_threshold=70,
        telegram=TelegramConfig(api_id=11111111, api_hash="test_api_hash", phone="+15551234567"),
        gemini=GeminiConfig(api_key="test_gemini_key"),
        notifications=NotificationConfig(
            desktop=True,
            telegram_bot=TelegramBotNotifyConfig(enabled=True, bot_token="123456:test", chat_id="987654321"),
        ),
        areas=[
            {
                "name": "Python Dev",
                "description": "Backend Python developer positions.",
                "keywords": ["python", "fastapi", "django"],
                "negative_keywords": ["unpaid", "intern"],
                "sources": ["pyjobs"],
            }
        ],
        config_path=sample_config_yaml,
        db_path=tmp_path / "telefeed.db",
        session_path=tmp_path / "telefeed.session",
    )


@pytest.fixture
def sample_area() -> Area:
    """Return a single sample Area object."""
    return Area(
        name="Backend Engineering",
        description="Backend engineering roles.",
        keywords=["python", "golang", "rust"],
        negative_keywords=["internship", "unpaid"],
        sources=["backend_jobs"],
    )
