"""
Unit tests for telefeed.notifications module (Desktop popups & Telegram Bot push).
"""

from unittest.mock import MagicMock, patch
import pytest

from telefeed.config import NotificationConfig, TelegramBotNotifyConfig
from telefeed.notifications import (
    NotificationManager,
    _send_desktop_notification_sync,
    _send_telegram_bot_sync,
)


import subprocess


@patch("shutil.which", return_value="/usr/bin/notify-send")
@patch("subprocess.run")
def test_send_desktop_notification_linux(mock_run, mock_which):
    with patch("platform.system", return_value="Linux"):
        res = _send_desktop_notification_sync("Title", "Message")
        assert res is True
        mock_run.assert_called_once_with(
            ["notify-send", "-a", "TeleFeed", "-u", "normal", "Title", "Message"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


@patch("subprocess.run")
def test_send_desktop_notification_darwin(mock_run):
    with patch("platform.system", return_value="Darwin"):
        res = _send_desktop_notification_sync("Title", "Message")
        assert res is True
        mock_run.assert_called_once()


@patch("subprocess.run")
def test_send_desktop_notification_windows(mock_run):
    with patch("platform.system", return_value="Windows"):
        res = _send_desktop_notification_sync("Title", "Message")
        assert res is True
        mock_run.assert_called_once()


@patch("urllib.request.urlopen")
def test_send_telegram_bot_sync_success(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    res = _send_telegram_bot_sync("token123", "chat456", "Hello")
    assert res is True
    mock_urlopen.assert_called_once()


def test_send_telegram_bot_sync_missing_params():
    assert _send_telegram_bot_sync("", "chat456", "Msg") is False
    assert _send_telegram_bot_sync("token123", "", "Msg") is False


@pytest.mark.asyncio
async def test_notification_manager_notify_match():
    cfg = NotificationConfig(
        desktop=True,
        telegram_bot=TelegramBotNotifyConfig(enabled=True, bot_token="token123", chat_id="chat456"),
    )
    mgr = NotificationManager(cfg)

    with patch("telefeed.notifications._send_desktop_notification_sync") as mock_desktop, \
         patch("telefeed.notifications._send_telegram_bot_sync") as mock_bot:
        
        await mgr.notify_match(
            area_name="Python Jobs",
            channel_title="PyChannel",
            text="Looking for a Python dev",
            score=0.9,
            url="https://t.me/py/1",
            ai_reason="Good match",
        )

        mock_desktop.assert_called_once()
        mock_bot.assert_called_once()


@pytest.mark.asyncio
async def test_notification_manager_notify_startup():
    cfg = NotificationConfig(
        desktop=True,
        telegram_bot=TelegramBotNotifyConfig(enabled=True, bot_token="token123", chat_id="chat456"),
    )
    mgr = NotificationManager(cfg)

    with patch("telefeed.notifications._send_desktop_notification_sync") as mock_desktop, \
         patch("telefeed.notifications._send_telegram_bot_sync") as mock_bot:
        
        await mgr.notify_startup(channel_count=5, area_count=2)

        mock_desktop.assert_called_once_with("TeleFeed Started 📡", "Monitoring 5 channel(s) across 2 area(s).")
        mock_bot.assert_called_once()
