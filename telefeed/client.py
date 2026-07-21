"""
Telethon client wrapper.

Handles:
  - Authentication (phone + OTP, session persistence)
  - Fetching historical messages from channels
  - Real-time message event handler for --live mode
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncGenerator, Callable, Optional

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError,
    SessionPasswordNeededError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
)
from telethon.tl.types import Message

from telefeed.display import console, print_error, print_info, print_success, print_warning


@dataclass
class ChannelInfo:
    """Metadata for a single subscribed channel or group."""
    key: str           # @username if available, else "id:<numeric_id>"
    title: str         # Human-readable name
    entity: object     # Pre-resolved Telethon entity
    unread_count: int  # Number of messages not yet read in Telegram
    is_broadcast: bool # True = broadcast channel, False = megagroup/supergroup


class TeleFeedClient:
    """Thin async wrapper around TelegramClient."""

    def __init__(
        self,
        session_file: str,
        api_id: int,
        api_hash: str,
        phone: str,
    ) -> None:
        self.phone = phone
        self._client = TelegramClient(session_file, api_id, api_hash)

    # ──────────────────────────────────────────────────────────────────────────
    # Auth
    # ──────────────────────────────────────────────────────────────────────────

    async def connect_and_auth(self) -> None:
        """Connect and interactively authenticate if needed."""
        try:
            await self._client.connect()
        except (TimeoutError, OSError, ConnectionError) as exc:
            print_error(
                "[bold]Could not connect to Telegram.[/bold]\n\n"
                "  Possible causes:\n"
                "  • Your [bold].env[/bold] still has placeholder credentials "
                "(TELEGRAM_API_ID / TELEGRAM_API_HASH).\n"
                "  • Your network blocks Telegram's MTProto protocol (common on\n"
                "    some corporate / university networks and certain countries).\n"
                "  • Telegram's servers are temporarily unreachable.\n\n"
                f"  Technical detail: {exc}\n\n"
                "  Steps to fix:\n"
                "  1. Make sure [bold].env[/bold] has your real API credentials from "
                "[link=https://my.telegram.org/apps]my.telegram.org/apps[/link].\n"
                "  2. If on a restricted network, try a VPN.\n"
                "  3. Run [bold]telefeed auth[/bold] to test the connection first."
            )
            raise SystemExit(1)

        if await self._client.is_user_authorized():
            me = await self._client.get_me()
            print_success(f"Already logged in as [bold]{me.first_name}[/bold] (@{me.username})")
            return

        print_info(f"Sending OTP to [bold]{self.phone}[/bold] …")
        await self._client.send_code_request(self.phone)

        code = console.input("[bold cyan]Enter the OTP code you received:[/bold cyan] ").strip()

        try:
            await self._client.sign_in(self.phone, code)
        except SessionPasswordNeededError:
            # 2FA is enabled
            pw = console.input("[bold cyan]Two-factor auth password:[/bold cyan] ").strip()
            await self._client.sign_in(password=pw)

        me = await self._client.get_me()
        print_success(f"Logged in as [bold]{me.first_name}[/bold] (@{me.username})")

    async def disconnect(self) -> None:
        await self._client.disconnect()

    # ──────────────────────────────────────────────────────────────────────────
    # Historical fetch
    # ──────────────────────────────────────────────────────────────────────────

    async def fetch_messages(
        self,
        channel,
        limit: Optional[int] = 100,
        min_id: int = 0,
        min_date: Optional[datetime] = None,
    ) -> AsyncGenerator[Message, None]:
        """
        Yield recent messages from *channel*.

        Args:
            channel  : Username string OR pre-resolved Telethon entity.
            limit    : Max messages to fetch (None = unlimited, use with min_date).
            min_id   : Only fetch messages with ID > this value.
            min_date : Stop yielding once a message is older than this datetime.
                       Pass a tz-aware datetime; messages are compared in UTC.

        Passing a pre-resolved entity avoids a second get_entity() call,
        which fails for private channels that have no public username.
        """
        display = getattr(channel, 'title', None) or f"@{channel}"
        try:
            if isinstance(channel, str):
                entity = await self._client.get_entity(channel)
            else:
                entity = channel
        except (UsernameInvalidError, UsernameNotOccupiedError):
            print_error(f"Channel not found: [bold]{display}[/bold]. Skipping.")
            return
        except ChannelPrivateError:
            print_error(f"Channel is private and you're not a member: [bold]{display}[/bold]. Skipping.")
            return
        except Exception as exc:
            print_error(f"Failed to get entity for {display}: {exc}")
            return

        # Normalise min_date to UTC-aware for comparison
        cutoff: Optional[datetime] = None
        if min_date is not None:
            cutoff = min_date if min_date.tzinfo else min_date.replace(tzinfo=timezone.utc)

        try:
            async for msg in self._client.iter_messages(
                entity,
                limit=limit,
                min_id=min_id,
                reverse=False,  # newest first — we stop early when we hit the cutoff
            ):
                if not isinstance(msg, Message) or not msg.text:
                    continue
                if cutoff is not None:
                    msg_date = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=timezone.utc)
                    if msg_date < cutoff:
                        return  # all older messages can be skipped
                yield msg
        except FloodWaitError as e:
            print_warning(f"Rate limited — waiting {e.seconds}s before continuing …")
            await asyncio.sleep(e.seconds)

    # ──────────────────────────────────────────────────────────────────────────
    # Live / real-time mode
    # ──────────────────────────────────────────────────────────────────────────

    async def listen_live(
        self,
        channels: list[tuple[str, any]],
        on_message: Callable[[str, Message], None],
    ) -> None:
        """
        Register a handler for new messages and run the event loop until Ctrl-C.

        *channels* is a list of (display_name, entity_or_username) pairs.
        Passing pre-resolved entities (from get_subscribed_channels) avoids
        a second get_entity() call that fails for private/no-username channels.

        *on_message* receives (display_name, Message).
        """
        resolved_entities: list = []
        resolved_names: list[str] = []

        for display_name, entity_or_username in channels:
            if isinstance(entity_or_username, str):
                # Explicit username from config — resolve it
                try:
                    entity = await self._client.get_entity(entity_or_username)
                    resolved_entities.append(entity)
                    resolved_names.append(display_name)
                except Exception as exc:
                    print_error(f"Skipping [bold]{display_name}[/bold] in live mode: {exc}")
            else:
                # Pre-resolved entity from get_subscribed_channels — use directly
                resolved_entities.append(entity_or_username)
                resolved_names.append(display_name)

        if not resolved_entities:
            print_error("No valid channels to watch. Exiting live mode.")
            return

        # Map entity ID → display name for the incoming message handler.
        # Telethon sometimes returns negative peer IDs (e.g. -1001234567890)
        # while entity.id is stored as the bare positive integer (1234567890).
        # We index both forms so lookups always succeed.
        channel_map: dict[int, str] = {}
        for e, name in zip(resolved_entities, resolved_names):
            channel_map[e.id] = name
            channel_map[-e.id] = name                      # negative peer form
            channel_map[-(e.id + 1_000_000_000_000)] = name  # supergroup form

        @self._client.on(events.NewMessage(chats=resolved_entities))
        async def _handler(event: events.NewMessage.Event) -> None:
            msg: Message = event.message
            if not msg.text:
                return
            ch_name = channel_map.get(event.chat_id) or channel_map.get(abs(event.chat_id), str(event.chat_id))
            result = on_message(ch_name, msg)
            if __import__("inspect").isawaitable(result):
                await result


        print_info(
            f"Watching [bold]{len(resolved_entities)}[/bold] channel(s) in real-time. "
            "Press [bold]Ctrl-C[/bold] to stop.\n"
        )
        await self._client.run_until_disconnected()


    # ──────────────────────────────────────────────────────────────────────────
    # Subscribed channel discovery
    # ──────────────────────────────────────────────────────────────────────────

    async def get_subscribed_channels(
        self,
        include_groups: bool = True,
    ) -> list[ChannelInfo]:
        """
        Return all channels (and megagroups) the user is subscribed to
        as a list of ChannelInfo objects.

        Each ChannelInfo carries:
          - key          : @username or "id:<numeric_id>" for private channels
          - title        : Human-readable name
          - entity       : Pre-resolved Telethon entity (no re-lookup needed)
          - unread_count : Number of unread messages in this dialog
          - is_broadcast : True for broadcast channels, False for groups

        Args:
            include_groups: If True (default), include supergroups / megagroups.
        """
        results: list[ChannelInfo] = []

        async for dialog in self._client.iter_dialogs():
            entity = dialog.entity

            is_broadcast = getattr(entity, "broadcast", False)
            is_megagroup = getattr(entity, "megagroup", False)

            if is_broadcast or (include_groups and is_megagroup):
                username = getattr(entity, "username", None)
                key = username if username else f"id:{entity.id}"
                title = dialog.title or key
                unread = getattr(dialog.dialog, "unread_count", 0) or 0

                results.append(ChannelInfo(
                    key=key,
                    title=title,
                    entity=entity,
                    unread_count=unread,
                    is_broadcast=is_broadcast,
                ))

        return results


def build_message_url(channel: str, message_id: int) -> str:
    """Construct a t.me link for a message."""
    return f"https://t.me/{channel}/{message_id}"
