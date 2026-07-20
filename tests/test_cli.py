"""
Integration & unit tests for telefeed.cli module.
Covers all CLI subcommands, flags, and options using Click's CliRunner.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from click.testing import CliRunner

from telefeed.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_version(runner: CliRunner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "TeleFeed" in result.output or "version" in result.output.lower()


def test_cli_init_default(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_config = tmp_path / "telefeed" / "config.yaml"
    monkeypatch.setattr("telefeed.cli.DEFAULT_CONFIG_PATH", fake_config)

    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    assert fake_config.exists()
    assert "Created configuration file" in result.output

    # Invoking again should warn that file exists
    result2 = runner.invoke(cli, ["init"])
    assert result2.exit_code == 0
    assert "already exists" in result2.output


def test_cli_init_local(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli, ["init", "--local"])
    assert result.exit_code == 0
    assert (tmp_path / "config.yaml").exists()


def test_cli_doctor(runner: CliRunner, sample_config_yaml: Path):
    result = runner.invoke(cli, ["doctor", "--config", str(sample_config_yaml)])
    assert result.exit_code == 0
    assert "TeleFeed Diagnostics" in result.output
    assert "Telegram API credentials present." in result.output


def test_cli_auth_missing_credentials(runner: CliRunner, tmp_path: Path):
    empty_config = tmp_path / "empty_config.yaml"
    empty_config.write_text("telegram: {}\n", encoding="utf-8")

    result = runner.invoke(cli, ["auth", "--config", str(empty_config)])
    assert result.exit_code == 1
    assert "Telegram credentials are missing" in result.output


@patch("telefeed.cli.TeleFeedClient")
def test_cli_auth_success(mock_client_cls, runner: CliRunner, sample_config_yaml: Path):
    mock_client = MagicMock()
    mock_client.connect_and_auth = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client_cls.return_value = mock_client

    result = runner.invoke(cli, ["auth", "--config", str(sample_config_yaml)])
    assert result.exit_code == 0
    assert "Authentication complete" in result.output


def test_cli_list_areas(runner: CliRunner, sample_config_yaml: Path):
    result = runner.invoke(cli, ["list-areas", "--config", str(sample_config_yaml)])
    assert result.exit_code == 0
    assert "Python Dev" in result.output
    assert "AI News" in result.output


def test_cli_show_matches(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "telefeed.db"
    config_file = tmp_path / "config.yaml"
    config_file.write_text("matcher: keywords\nareas: []\n", encoding="utf-8")

    # Seed DB
    from telefeed.store import init_db, save_match
    init_db(str(db_file))
    save_match(str(db_file), "Python Dev", "pyjobs", 1, "Hiring Python backend dev", "https://t.me/pyjobs/1")

    monkeypatch.setenv("DB_PATH", str(db_file))
    result = runner.invoke(cli, ["show-matches", "--config", str(config_file), "--area", "Python Dev", "--status", "new", "--limit", "10"])
    assert result.exit_code == 0
    assert "Saved Matches" in result.output or "pyjobs" in result.output


def test_cli_service_subcommands(runner: CliRunner):
    with patch("telefeed.cli.install_service") as mock_inst:
        runner.invoke(cli, ["service", "install"])
        mock_inst.assert_called_once()

    with patch("telefeed.cli.uninstall_service") as mock_uninst:
        runner.invoke(cli, ["service", "uninstall"])
        mock_uninst.assert_called_once()

    with patch("telefeed.cli.service_action") as mock_action:
        runner.invoke(cli, ["service", "start"])
        mock_action.assert_called_with("start")

        runner.invoke(cli, ["service", "stop"])
        mock_action.assert_called_with("stop")

        runner.invoke(cli, ["service", "restart"])
        mock_action.assert_called_with("restart")

        runner.invoke(cli, ["service", "status"])
        mock_action.assert_called_with("status")

    with patch("telefeed.cli.service_logs") as mock_logs:
        runner.invoke(cli, ["service", "logs"])
        mock_logs.assert_called_once()


@patch("telefeed.cli.TeleFeedClient")
def test_cli_fetch_flags(mock_client_cls, runner: CliRunner, sample_config_yaml: Path, tmp_path: Path):
    mock_client = MagicMock()
    mock_client.connect_and_auth = AsyncMock()
    mock_client.disconnect = AsyncMock()

    # Mock get_subscribed_channels
    from telefeed.client import ChannelInfo
    ch = ChannelInfo(key="pyjobs", title="Python Jobs", entity=None, unread_count=0, is_broadcast=True)
    mock_client.get_subscribed_channels = AsyncMock(return_value=[ch])
    
    # Mock empty fetch_messages async generator
    async def _async_gen(*args, **kwargs):
        if False:
            yield None

    mock_client.fetch_messages = _async_gen
    mock_client_cls.return_value = mock_client

    # Test fetch with flags: --limit, --area, --no-save, --no-groups, --no-ai, --notify
    result = runner.invoke(
        cli,
        [
            "fetch",
            "--config", str(sample_config_yaml),
            "--limit", "50",
            "--area", "Python Dev",
            "--no-save",
            "--no-groups",
            "--no-ai",
            "--notify",
        ],
    )
    assert result.exit_code == 0
    assert "Using Keyword matching" in result.output
