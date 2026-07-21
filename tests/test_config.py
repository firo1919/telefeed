"""
Unit tests for telefeed.config module (XDG paths, configuration loading & parsing).
"""

import os
from pathlib import Path
import pytest

from telefeed.config import (
    CONFIG_TEMPLATE,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_SESSION_FILE,
    get_config_path,
    get_db_path,
    get_session_path,
    load_telefeed_config,
)


def test_get_config_path_custom(tmp_path: Path):
    custom_path = str(tmp_path / "custom.yaml")
    resolved = get_config_path(custom_path)
    assert resolved == Path(custom_path).resolve()


def test_get_config_path_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = str(tmp_path / "env_config.yaml")
    monkeypatch.setenv("CONFIG_PATH", env_path)
    resolved = get_config_path()
    assert resolved == Path(env_path).resolve()


def test_get_config_path_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    cwd_config = tmp_path / "config.yaml"
    cwd_config.touch()
    resolved = get_config_path()
    assert resolved == cwd_config


def test_get_config_path_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    resolved = get_config_path()
    assert resolved == DEFAULT_CONFIG_PATH


def test_get_db_path_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_db = str(tmp_path / "custom.db")
    monkeypatch.setenv("DB_PATH", env_db)
    assert get_db_path() == Path(env_db).resolve()


def test_get_session_path_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_sess = str(tmp_path / "custom.session")
    monkeypatch.setenv("SESSION_FILE", env_sess)
    assert get_session_path() == Path(env_sess).resolve()


def test_load_telefeed_config_nonexistent(tmp_path: Path):
    nonexistent = tmp_path / "does_not_exist.yaml"
    cfg = load_telefeed_config(str(nonexistent))
    assert cfg.config_path == nonexistent
    assert cfg.telegram.api_id == 0
    assert cfg.matcher == "keywords"


def test_load_telefeed_config_valid(sample_config_yaml: Path):
    cfg = load_telefeed_config(str(sample_config_yaml))
    assert cfg.matcher == "ai"
    assert cfg.ai_threshold == 70
    assert cfg.telegram.api_id == 11111111
    assert cfg.telegram.api_hash == "test_api_hash"
    assert cfg.telegram.phone == "+15551234567"
    # ai: section
    assert cfg.ai.provider == "gemini"
    assert cfg.ai.model == "gemini-2.5-flash"
    assert cfg.ai.api_key == "test_gemini_key"
    assert cfg.notifications.desktop is True
    assert cfg.notifications.telegram_bot.enabled is True
    assert cfg.notifications.telegram_bot.bot_token == "123456:test_bot_token"
    assert len(cfg.areas) == 2


def test_load_telefeed_config_env_fallbacks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_file = tmp_path / "minimal.yaml"
    config_file.write_text("matcher: keywords\nareas: []\n", encoding="utf-8")

    monkeypatch.setenv("TELEGRAM_API_ID", "999999")
    monkeypatch.setenv("TELEGRAM_API_HASH", "env_hash")
    monkeypatch.setenv("TELEGRAM_PHONE", "+1999888777")
    monkeypatch.setenv("GEMINI_API_KEY", "env_gemini_key")

    cfg = load_telefeed_config(str(config_file))
    assert cfg.telegram.api_id == 999999
    assert cfg.telegram.api_hash == "env_hash"
    assert cfg.telegram.phone == "+1999888777"
    assert cfg.ai.api_key == "env_gemini_key"


def test_load_telefeed_config_openai_provider(tmp_path: Path):
    config_file = tmp_path / "openai_config.yaml"
    config_file.write_text(
        "matcher: ai\nai_threshold: 75\n"
        "ai:\n"
        "  provider: openai\n"
        "  model: gpt-4o-mini\n"
        "  api_key: sk-test-key\n"
        "telegram:\n  api_id: 0\n  api_hash: ''\n  phone: ''\n"
        "areas: []\n",
        encoding="utf-8",
    )
    cfg = load_telefeed_config(str(config_file))
    assert cfg.ai.provider == "openai"
    assert cfg.ai.model == "gpt-4o-mini"
    assert cfg.ai.api_key == "sk-test-key"


def test_load_telefeed_config_ollama_defaults(tmp_path: Path):
    config_file = tmp_path / "ollama_config.yaml"
    config_file.write_text(
        "matcher: ai\n"
        "ai:\n"
        "  provider: ollama\n"
        "  base_url: http://localhost:11434/v1\n"
        "telegram:\n  api_id: 0\n  api_hash: ''\n  phone: ''\n"
        "areas: []\n",
        encoding="utf-8",
    )
    cfg = load_telefeed_config(str(config_file))
    assert cfg.ai.provider == "ollama"
    assert cfg.ai.model == "llama3.2"   # auto-default for ollama
    assert cfg.ai.base_url == "http://localhost:11434/v1"


def test_load_telefeed_config_legacy_gemini_section(tmp_path: Path):
    """Configs with the old 'gemini:' section should still work."""
    config_file = tmp_path / "legacy.yaml"
    config_file.write_text(
        "matcher: ai\n"
        "gemini:\n"
        "  api_key: legacy_key\n"
        "telegram:\n  api_id: 0\n  api_hash: ''\n  phone: ''\n"
        "areas: []\n",
        encoding="utf-8",
    )
    cfg = load_telefeed_config(str(config_file))
    # Falls back to gemini provider with key from legacy section
    assert cfg.ai.api_key == "legacy_key"
    assert cfg.ai.provider == "gemini"


def test_config_template_validity():
    assert "matcher: ai" in CONFIG_TEMPLATE
    assert "telegram:" in CONFIG_TEMPLATE
    assert "notifications:" in CONFIG_TEMPLATE
    assert "areas:" in CONFIG_TEMPLATE
    assert "ai:" in CONFIG_TEMPLATE
    assert "provider: gemini" in CONFIG_TEMPLATE
    assert "openai" in CONFIG_TEMPLATE or "openrouter" in CONFIG_TEMPLATE or "anthropic" in CONFIG_TEMPLATE
