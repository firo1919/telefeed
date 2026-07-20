"""
Notification dispatch engine for TeleFeed.

Supports:
  1. Desktop OS Notifications (via native notify-send / osascript / PowerShell)
  2. Telegram Bot Push Alerts (via Telegram Bot API HTTP requests)
"""

import asyncio
import html
import json
import logging
import os
import platform
import shutil
import subprocess
import urllib.parse
import urllib.request
from typing import Optional

from telefeed.config import NotificationConfig
from telefeed.display import print_info, print_warning

logger = logging.getLogger("telefeed.notifications")


def _send_desktop_notification_sync(title: str, message: str, url: Optional[str] = None) -> bool:
    """Send a native OS desktop notification (synchronous)."""
    system = platform.system().lower()

    try:
        if system == "linux":
            # Check for notify-send executable
            if shutil.which("notify-send"):
                cmd = ["notify-send", "-a", "TeleFeed", "-u", "normal", title, message]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
        elif system == "darwin":
            # macOS osascript
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        elif system == "windows":
            # PowerShell Toast
            ps_script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $textNodes = $template.GetElementsByTagName("text")
            $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) | Out-Null
            $textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) | Out-Null
            $toast = [Windows.UI.Notifications.ToastNotification]::$new($template)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("TeleFeed").Show($toast)
            """
            subprocess.run(["powershell", "-Command", ps_script], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except Exception as exc:
        logger.debug(f"Desktop notification failed: {exc}")
    
    return False


def _send_telegram_bot_sync(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a notification message via Telegram Bot API (synchronous)."""
    if not bot_token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        print_warning(f"Telegram Bot notification failed: {exc}")
        return False


class NotificationManager:
    """Dispatches notifications asynchronously across configured backends."""

    def __init__(self, config: NotificationConfig) -> None:
        self.config = config

    async def notify_match(
        self,
        area_name: str,
        channel_title: str,
        text: str,
        score: float,
        url: Optional[str] = None,
        ai_reason: Optional[str] = None,
    ) -> None:
        """Dispatch match notification to all enabled channels."""
        score_percent = f"{score:.0%}"
        snippet = text.strip().replace("\n", " ")
        if len(snippet) > 250:
            snippet = snippet[:250] + "…"

        # 1. Desktop Notification
        if self.config.desktop:
            title = f"TeleFeed: {area_name}"
            msg_body = f"[{channel_title}] ({score_percent} match)\n{snippet}"
            await asyncio.to_thread(_send_desktop_notification_sync, title, msg_body, url)

        # 2. Telegram Bot Notification
        if self.config.telegram_bot.enabled and self.config.telegram_bot.bot_token:
            clean_title = html.escape(channel_title)
            clean_area = html.escape(area_name)
            clean_snippet = html.escape(snippet)

            bot_msg_parts = [
                f"📡 <b>TeleFeed Alert</b>: <i>{clean_area}</i>",
                f"<b>Channel:</b> {clean_title}",
                f"<b>Relevance:</b> {score_percent}",
            ]
            if ai_reason:
                bot_msg_parts.append(f"🤖 <b>AI Reason:</b> {html.escape(ai_reason)}")

            bot_msg_parts.append(f"\n{clean_snippet}")

            if url:
                bot_msg_parts.append(f'\n<a href="{url}">🔗 Open in Telegram</a>')

            bot_msg = "\n".join(bot_msg_parts)
            
            await asyncio.to_thread(
                _send_telegram_bot_sync,
                self.config.telegram_bot.bot_token,
                self.config.telegram_bot.chat_id,
                bot_msg,
            )

    async def notify_startup(self, channel_count: int, area_count: int) -> None:
        """Send an initial startup notification signifying monitoring has started."""
        # 1. Desktop Notification
        if self.config.desktop:
            title = "TeleFeed Started 📡"
            msg_body = f"Monitoring {channel_count} channel(s) across {area_count} area(s)."
            await asyncio.to_thread(_send_desktop_notification_sync, title, msg_body)

        # 2. Telegram Bot Notification
        if self.config.telegram_bot.enabled and self.config.telegram_bot.bot_token:
            bot_msg = (
                "📡 <b>TeleFeed Monitoring Active</b>\n"
                f"TeleFeed has started watching <b>{channel_count}</b> channel(s) "
                f"across <b>{area_count}</b> topic area(s)."
            )
            await asyncio.to_thread(
                _send_telegram_bot_sync,
                self.config.telegram_bot.bot_token,
                self.config.telegram_bot.chat_id,
                bot_msg,
            )

