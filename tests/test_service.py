"""
Unit tests for telefeed.service module (Systemd user service installer & manager).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from telefeed.service import (
    SERVICE_FILE_PATH,
    get_telefeed_exec,
    install_service,
    service_action,
    service_logs,
    uninstall_service,
)


def test_get_telefeed_exec():
    with patch("shutil.which", return_value="/usr/local/bin/telefeed"):
        assert get_telefeed_exec() == "/usr/local/bin/telefeed"

    with patch("shutil.which", return_value=None):
        exec_str = get_telefeed_exec()
        assert "-m telefeed" in exec_str


@patch("shutil.which", return_value="/bin/systemctl")
@patch("subprocess.run")
def test_install_service_success(mock_run, mock_which, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_unit_dir = tmp_path / "systemd" / "user"
    fake_unit_path = fake_unit_dir / "telefeed.service"

    monkeypatch.setattr("telefeed.service.SYSTEMD_USER_DIR", fake_unit_dir)
    monkeypatch.setattr("telefeed.service.SERVICE_FILE_PATH", fake_unit_path)

    res = install_service()
    assert res is True
    assert fake_unit_path.exists()
    content = fake_unit_path.read_text(encoding="utf-8")
    assert "ExecStart=" in content
    assert "fetch --live --notify" in content
    assert mock_run.call_count == 2


@patch("shutil.which", return_value=None)
def test_install_service_no_systemctl(mock_which):
    res = install_service()
    assert res is False


@patch("subprocess.run")
def test_uninstall_service(mock_run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_unit_path = tmp_path / "telefeed.service"
    fake_unit_path.touch()

    monkeypatch.setattr("telefeed.service.SERVICE_FILE_PATH", fake_unit_path)

    res = uninstall_service()
    assert res is True
    assert not fake_unit_path.exists()
    assert mock_run.call_count == 2


@patch("subprocess.run")
def test_service_action(mock_run):
    service_action("start")
    mock_run.assert_called_once_with(["systemctl", "--user", "start", "telefeed.service"])

    mock_run.reset_mock()
    service_action("invalid_action")
    mock_run.assert_not_called()


@patch("subprocess.run")
def test_service_logs(mock_run):
    service_logs()
    mock_run.assert_called_once_with(["journalctl", "--user", "-u", "telefeed.service", "-n", "50", "-f"])
