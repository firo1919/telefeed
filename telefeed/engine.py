"""
Core feed processing pipeline for TeleFeed.
Handles channel discovery, message ingestion, scoring, and notification dispatch.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from telefeed.ai_filter import BaseScorer, ai_check_all_areas
from telefeed.client import TeleFeedClient, build_message_url
from telefeed.config import TeleFeedConfig
from telefeed.display import (
    console,
    print_info,
    print_match,
    print_section,
    print_success,
    print_warning,
)
from telefeed.filters import Area, check_all_areas
from telefeed.notifications import NotificationManager
from telefeed.store import check_and_mark_seen, save_match


class TeleFeedEngine:
    def __init__(
        self,
        client: TeleFeedClient,
        config: TeleFeedConfig,
        areas: list[Area],
        notifier: Optional[NotificationManager] = None,
        ai_scorer: Optional[BaseScorer] = None,
    ):
        self.client = client
        self.config = config
        self.db_path = str(config.db_path)
        self.areas = areas
        self.notifier = notifier
        self.ai_scorer = ai_scorer

        self.match_count = 0
        self.total_checked = 0
        self.source_area_map: dict[str, dict] = {}

    async def build_source_map(self, no_groups: bool) -> dict:
        """Resolve and build the mapping of channels to the areas watching them."""
        source_map: dict[str, dict] = {}
        areas_watching_all = [a for a in self.areas if not a.sources]
        areas_with_sources = [a for a in self.areas if a.sources]

        def _add(key: str, area_obj, entity=None, title: str = "",
                 is_broadcast: bool = False, unread_count: int = 0) -> None:
            if key not in source_map:
                source_map[key] = {
                    "areas": [],
                    "entity": entity,
                    "title": title or key,
                    "is_broadcast": is_broadcast,
                    "unread_count": unread_count,
                }
            if area_obj not in source_map[key]["areas"]:
                source_map[key]["areas"].append(area_obj)

        for a in areas_with_sources:
            for src in a.sources:
                ch = src.lstrip("@")
                _add(ch, a, entity=None, title=ch)

        if areas_watching_all:
            print_info(
                f"[bold]{len(areas_watching_all)}[/bold] area(s) have no sources — "
                "discovering your subscribed channels…"
            )
            subscribed = await self.client.get_subscribed_channels(
                include_groups=not no_groups
            )
            print_success(
                f"Found [bold]{len(subscribed)}[/bold] subscribed channel(s)/group(s)."
            )
            for ch_info in subscribed:
                for a in areas_watching_all:
                    _add(
                        ch_info.key, a,
                        entity=ch_info.entity,
                        title=ch_info.title,
                        is_broadcast=ch_info.is_broadcast,
                        unread_count=ch_info.unread_count,
                    )

        self.source_area_map = source_map
        return source_map

    async def _process_message(self, channel_key: str, title: str, msg, no_save: bool):
        """Run a single message through the filters and handle matches."""
        already_seen = await asyncio.to_thread(
            check_and_mark_seen, self.db_path, channel_key, msg.id
        )
        if already_seen:
            return False

        areas_for_channel = self.source_area_map.get(channel_key, {}).get("areas", [])
        if not areas_for_channel:
            return False

        if self.ai_scorer:
            results = await ai_check_all_areas(areas_for_channel, msg.text, self.ai_scorer, self.config.threshold)
        else:
            results = check_all_areas(areas_for_channel, msg.text, threshold=self.config.threshold)

        if not results:
            return False

        for result in results:
            self.match_count += 1
            url = build_message_url(channel_key, msg.id)
            ts = msg.date.replace(tzinfo=None) if msg.date else None

            print_match(
                area_name=result.area.name,
                channel=title,
                message_id=msg.id,
                text=msg.text,
                score=result.score,
                matched_keywords=result.matched_keywords,
                url=url,
                timestamp=ts,
                ai_reason=result.ai_reason,
            )

            if self.notifier:
                await self.notifier.notify_match(
                    area_name=result.area.name,
                    channel_title=title,
                    text=msg.text,
                    score=result.score,
                    url=url,
                    ai_reason=result.ai_reason,
                )

            if not no_save:
                await asyncio.to_thread(
                    save_match,
                    db_path=self.db_path,
                    area=result.area.name,
                    channel=channel_key,
                    message_id=msg.id,
                    text=msg.text,
                    url=url,
                    score=result.score,
                    ai_reason=result.ai_reason,
                )
        return True

    async def run_fetch(self, limit: int, no_groups: bool, no_save: bool) -> None:
        """Fetch historical messages up to the limit and exit."""
        await self.client.connect_and_auth()
        await self.build_source_map(no_groups)

        if not self.source_area_map:
            print_warning("No channels to watch. Subscribe to channels or add sources to config.yaml.")
            return

        print_section(f"Scanning {len(self.source_area_map)} channel(s)")

        for channel_key, info in self.source_area_map.items():
            entity = info["entity"]
            title = info["title"]

            print_section(f"Fetching {title}")
            msg_count = 0
            channel_arg = entity if entity is not None else channel_key

            async for msg in self.client.fetch_messages(channel_arg, limit=limit):
                self.total_checked += 1
                msg_count += 1
                await self._process_message(channel_key, title, msg, no_save)

            print_info(f"Checked {msg_count} message(s) from {title}")

        if self.match_count == 0:
            print_warning("No matches found. Try adjusting your keywords in config.yaml.")
        else:
            print_success(f"Found [bold]{self.match_count}[/bold] match(es) from {self.total_checked} message(s) checked.")

    async def run_live(self, no_groups: bool, no_save: bool, backfill_days: int) -> None:
        """Run a backfill of recent unread history, then watch live indefinitely."""
        await self.client.connect_and_auth()
        await self.build_source_map(no_groups)

        if not self.source_area_map:
            print_warning("No channels to watch. Subscribe to channels or add sources to config.yaml.")
            return

        if self.notifier:
            await self.notifier.notify_startup(len(self.source_area_map), len(self.areas))

        # 1. Backfill phase
        backfill_cutoff = datetime.now(timezone.utc) - timedelta(days=backfill_days)
        backfill_total = 0
        backfill_matches = 0

        print_section(
            f"Backfilling {len(self.source_area_map)} channel(s) "
            f"(history: {backfill_days}d)"
        )

        for channel_key, info in self.source_area_map.items():
            entity = info["entity"]
            title = info["title"]

            channel_arg = entity if entity is not None else channel_key
            fetch_kwargs = dict(limit=None, min_date=backfill_cutoff)
            scope_label = f"{backfill_days}d history"

            msg_count = 0
            async for msg in self.client.fetch_messages(channel_arg, **fetch_kwargs):
                backfill_total += 1
                msg_count += 1
                # Track backfill matches separately from live matches
                start_matches = self.match_count
                await self._process_message(channel_key, title, msg, no_save)
                if self.match_count > start_matches:
                    backfill_matches += (self.match_count - start_matches)

            if msg_count > 0:
                print_info(f"  {title} ({scope_label}): {msg_count} msgs, {backfill_matches} match(es)")

        if backfill_matches == 0:
            print_info("Backfill complete — no matches in history. Now watching live…")
        else:
            print_success(
                f"Backfill complete — [bold]{backfill_matches}[/bold] match(es) "
                f"from {backfill_total} message(s). Now watching live…"
            )

        # 2. Live listen phase
        channel_pairs = [
            (info["title"], info["entity"] if info["entity"] is not None else ch_key)
            for ch_key, info in self.source_area_map.items()
        ]

        async def _async_on_message(display_name: str, msg) -> None:
            ch_key = next(
                (k for k, v in self.source_area_map.items() if v["title"] == display_name),
                display_name,
            )
            matched = await self._process_message(ch_key, display_name, msg, no_save)
            if not matched:
                console.print(f"  [dim]Skipped message from @{display_name} (no match)[/dim]")

        await self.client.listen_live(channel_pairs, _async_on_message)
