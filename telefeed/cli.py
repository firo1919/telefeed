"""
TeleFeed CLI entry point.

Commands:
  auth          Log in to Telegram and save the session.
  fetch         Fetch recent messages from all configured sources and print matches.
  list-areas    Show all configured areas of concern.
  show-matches  Display previously saved matches from the local database.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import click
import yaml
from dotenv import load_dotenv
from rich.progress import Progress, SpinnerColumn, TextColumn

from telefeed import __app_name__, __version__
from telefeed.ai_filter import AIScorer, ai_check_all_areas
from telefeed.client import ChannelInfo, TeleFeedClient, build_message_url
from telefeed.display import (
    console,
    print_areas,
    print_banner,
    print_error,
    print_info,
    print_match,
    print_matches_table,
    print_section,
    print_success,
    print_warning,
)
from telefeed.filters import check_all_areas, load_areas_from_config, load_matcher_config
from telefeed.store import (
    get_matches,
    init_db,
    is_seen,
    mark_seen,
    save_match,
)

# Load .env from project root
load_dotenv()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print_error(
            f"Missing environment variable [bold]{key}[/bold]. "
            f"Copy [bold].env.example[/bold] → [bold].env[/bold] and fill it in."
        )
        raise SystemExit(1)
    return val


def _load_config(config_path: str) -> dict:
    p = Path(config_path)
    if not p.exists():
        print_error(f"Config file not found: [bold]{config_path}[/bold]")
        raise SystemExit(1)
    with p.open() as f:
        return yaml.safe_load(f) or {}


def _build_client(config_path: str) -> tuple[TeleFeedClient, str, str]:
    """Build TeleFeedClient from env vars. Returns (client, session_file, db_path)."""
    api_id_str = _require_env("TELEGRAM_API_ID")
    api_hash = _require_env("TELEGRAM_API_HASH")
    phone = _require_env("TELEGRAM_PHONE")

    # Detect un-edited placeholder values from .env.example
    if api_id_str == "12345678" or api_hash == "your_api_hash_here":
        print_error(
            "[bold].env still contains placeholder credentials.[/bold]\n\n"
            "  Please set your real Telegram API credentials:\n"
            "  1. Go to [link=https://my.telegram.org/apps]https://my.telegram.org/apps[/link]\n"
            "  2. Log in and click [bold]'API development tools'[/bold]\n"
            "  3. Copy your [bold]api_id[/bold] and [bold]api_hash[/bold] into [bold].env[/bold]"
        )
        raise SystemExit(1)

    try:
        api_id = int(api_id_str)
    except ValueError:
        print_error(f"TELEGRAM_API_ID must be a number, got: [bold]{api_id_str!r}[/bold]")
        raise SystemExit(1)

    session_file = os.getenv("SESSION_FILE", "telefeed.session")
    db_path = os.getenv("DB_PATH", "telefeed.db")
    return TeleFeedClient(session_file, api_id, api_hash, phone), session_file, db_path


# ──────────────────────────────────────────────────────────────────────────────
# CLI group
# ──────────────────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(__version__, prog_name=__app_name__)
def cli() -> None:
    """TeleFeed — Personalized Telegram feed aggregator."""
    print_banner()


# ──────────────────────────────────────────────────────────────────────────────
# auth
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
def auth() -> None:
    """Log in to Telegram and save your session."""
    config_path = os.getenv("CONFIG_PATH", "config.yaml")
    client, session_file, _ = _build_client(config_path)

    print_info(f"Session will be saved to [bold]{session_file}[/bold]")

    async def _run():
        await client.connect_and_auth()
        await client.disconnect()

    asyncio.run(_run())
    print_success("Authentication complete. You won't need to log in again.")


# ──────────────────────────────────────────────────────────────────────────────
# list-areas
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("list-areas")
@click.option("--config", default=None, help="Path to config.yaml (overrides .env)")
def list_areas(config: Optional[str]) -> None:
    """Show all configured areas of concern."""
    config_path = config or os.getenv("CONFIG_PATH", "config.yaml")
    raw = _load_config(config_path)
    areas = load_areas_from_config(raw)
    print_areas(areas)


# ──────────────────────────────────────────────────────────────────────────────
# fetch
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--config", default=None, help="Path to config.yaml (overrides .env)")
@click.option("--limit", default=100, show_default=True, help="Max messages per channel per run")
@click.option("--live", is_flag=True, default=False, help="Keep running and watch for new messages")
@click.option("--area", default=None, help="Only run this specific area (by name)")
@click.option("--no-save", is_flag=True, default=False, help="Print matches but don't save to DB")
@click.option("--no-groups", is_flag=True, default=False, help="Exclude supergroups from auto-discovery")
@click.option("--backfill-days", default=7, show_default=True, help="In --live mode: days of history to scan on public channels before watching")
@click.option("--smart", is_flag=True, default=False, help="Force AI matching mode (overrides config.yaml)")
@click.option("--no-ai", is_flag=True, default=False, help="Force keyword matching mode (overrides config.yaml)")
def fetch(
    config: Optional[str],
    limit: int,
    live: bool,
    area: Optional[str],
    no_save: bool,
    no_groups: bool,
    backfill_days: int,
    smart: bool,
    no_ai: bool,
) -> None:
    """Fetch messages from subscribed channels and print matches.

    If an area in config.yaml has no 'sources' list, TeleFeed automatically
    uses ALL channels and supergroups you are subscribed to on Telegram.
    Add explicit 'sources' to an area to restrict it to specific channels.
    """
    config_path = config or os.getenv("CONFIG_PATH", "config.yaml")
    raw = _load_config(config_path)
    all_areas = load_areas_from_config(raw)

    if not all_areas:
        print_error("No areas configured. Add some to [bold]config.yaml[/bold] first.")
        raise SystemExit(1)

    # Filter to a single area if --area was given
    if area:
        all_areas = [a for a in all_areas if a.name.lower() == area.lower()]
        if not all_areas:
            print_error(f"No area named [bold]{area!r}[/bold] found in config.")
            raise SystemExit(1)

    # Resolve matching mode
    config_matcher, ai_threshold = load_matcher_config(raw)
    matcher = config_matcher
    if smart:
        matcher = "ai"
    if no_ai:
        matcher = "keywords"

    ai_scorer = None
    if matcher == "ai":
        try:
            ai_scorer = AIScorer.from_env()
            print_info(f"Using AI matching (Gemini) — threshold: {ai_threshold}")
        except ValueError as e:
            print_error(str(e))
            raise SystemExit(1)
    else:
        print_info("Using Keyword matching")

    client, _, db_path = _build_client(config_path)
    init_db(db_path)

    # Separate areas that need auto-discovery vs. explicit sources
    areas_watching_all = [a for a in all_areas if not a.sources]
    areas_with_sources = [a for a in all_areas if a.sources]

    async def _build_source_map() -> dict:
        """
        Build channel_key -> {areas, entity, title} map.

        For auto-discovered channels the pre-resolved entity is stored so we
        never need a second get_entity() call (which fails for private channels
        that have no public username).
        """
        # Each entry: {"areas": [...], "entity": <entity or None>, "title": str}
        source_map: dict[str, dict] = {}

        def _add(key: str, area, entity=None, title: str = "",
                 is_broadcast: bool = False, unread_count: int = 0) -> None:
            if key not in source_map:
                source_map[key] = {
                    "areas": [],
                    "entity": entity,
                    "title": title or key,
                    "is_broadcast": is_broadcast,
                    "unread_count": unread_count,
                }
            if area not in source_map[key]["areas"]:
                source_map[key]["areas"].append(area)

        # 1. Explicit sources from config (just usernames, no pre-resolved entity)
        for a in areas_with_sources:
            for src in a.sources:
                ch = src.lstrip("@")
                _add(ch, a, entity=None, title=ch)

        # 2. Auto-discover subscribed channels for areas with no sources
        if areas_watching_all:
            print_info(
                f"[bold]{len(areas_watching_all)}[/bold] area(s) have no sources — "
                "discovering your subscribed channels…"
            )
            subscribed = await client.get_subscribed_channels(
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

        return source_map

    match_count = 0
    total_checked = 0

    # ─── Historical fetch ────────────────────────────────────────────────────
    async def _run_fetch() -> None:
        nonlocal match_count, total_checked
        await client.connect_and_auth()

        source_area_map = await _build_source_map()

        if not source_area_map:
            print_warning("No channels to watch. Subscribe to some channels on Telegram or add sources to config.yaml.")
            return

        print_section(f"Scanning {len(source_area_map)} channel(s)")

        for channel_key, info in source_area_map.items():
            areas_for_channel = info["areas"]
            entity = info["entity"]  # None for explicit-source channels (username-based)
            title = info["title"]

            print_section(f"Fetching {title}")

            msg_count = 0
            # Pass entity directly when available (avoids failing re-lookup)
            channel_arg = entity if entity is not None else channel_key
            async for msg in client.fetch_messages(channel_arg, limit=limit):
                total_checked += 1
                msg_count += 1

                # Use channel_key (not entity) as the dedup / storage key
                if is_seen(db_path, channel_key, msg.id):
                    continue
                mark_seen(db_path, channel_key, msg.id)

                if ai_scorer:
                    results = await ai_check_all_areas(areas_for_channel, msg.text, ai_scorer, ai_threshold)
                else:
                    results = check_all_areas(areas_for_channel, msg.text)

                for result in results:
                    match_count += 1
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

                    if not no_save:
                        save_match(
                            db_path=db_path,
                            area=result.area.name,
                            channel=channel_key,
                            message_id=msg.id,
                            text=msg.text,
                            url=url,
                        )

            print_info(f"Checked {msg_count} message(s) from {title}")

        if match_count == 0:
            print_warning(
                "No matches found. Try adjusting your keywords in [bold]config.yaml[/bold]."
            )
        else:
            print_success(f"Found [bold]{match_count}[/bold] match(es) from {total_checked} message(s) checked.")

    # ─── Live mode ───────────────────────────────────────────────────────────
    async def _run_live() -> None:
        nonlocal match_count
        await client.connect_and_auth()

        source_area_map = await _build_source_map()

        if not source_area_map:
            print_warning("No channels to watch. Subscribe to some channels on Telegram or add sources to config.yaml.")
            return

        # ── Backfill ──────────────────────────────────────────────────────────
        # Before watching live, catch up on history:
        #   • Broadcast channels → last `backfill_days` days
        #   • Groups/supergroups → unread messages only
        backfill_cutoff = datetime.now(timezone.utc) - timedelta(days=backfill_days)
        backfill_total = 0
        backfill_matches = 0

        print_section(
            f"Backfilling {len(source_area_map)} channel(s) "
            f"(channels: {backfill_days}d history  |  groups: unread only)"
        )

        for channel_key, info in source_area_map.items():
            areas_for_channel = info["areas"]
            entity = info["entity"]
            title = info["title"]
            is_broadcast = info.get("is_broadcast", False)
            unread = info.get("unread_count", 0)

            channel_arg = entity if entity is not None else channel_key

            if is_broadcast:
                # Public broadcast channel → scan backfill_days of history
                fetch_kwargs = dict(limit=None, min_date=backfill_cutoff)
                scope_label = f"{backfill_days}d history"
            elif unread > 0:
                # Group/supergroup → only fetch unread messages (cap at 500)
                fetch_kwargs = dict(limit=min(unread, 500))
                scope_label = f"{unread} unread"
            else:
                # Group with nothing unread — skip
                continue

            msg_count = 0
            async for msg in client.fetch_messages(channel_arg, **fetch_kwargs):
                backfill_total += 1
                msg_count += 1

                if is_seen(db_path, channel_key, msg.id):
                    continue
                mark_seen(db_path, channel_key, msg.id)

                if ai_scorer:
                    results = await ai_check_all_areas(areas_for_channel, msg.text, ai_scorer, ai_threshold)
                else:
                    results = check_all_areas(areas_for_channel, msg.text)

                for result in results:
                    backfill_matches += 1
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
                    if not no_save:
                        save_match(
                            db_path=db_path,
                            area=result.area.name,
                            channel=channel_key,
                            message_id=msg.id,
                            text=msg.text,
                            url=url,
                        )

            if msg_count > 0:
                print_info(f"  {title} ({scope_label}): {msg_count} msgs, {backfill_matches} match(es)")

        if backfill_matches == 0:
            print_info("Backfill complete — no matches in history. Now watching live…")
        else:
            print_success(
                f"Backfill complete — [bold]{backfill_matches}[/bold] match(es) "
                f"from {backfill_total} message(s). Now watching live…"
            )

        # ── Live listener ─────────────────────────────────────────────────────
        # Build (display_name, entity_or_username) pairs for listen_live().
        # For auto-discovered channels: pass entity directly (avoids re-lookup failures).
        # For explicit-source channels: pass username string (resolved inside listen_live).
        channel_pairs = [
            (info["title"], info["entity"] if info["entity"] is not None else ch_key)
            for ch_key, info in source_area_map.items()
        ]

        def _on_message(display_name: str, msg) -> None:
            # We must use asyncio.create_task here if we have an async handler because
            # telethon event handlers can be async but we need to ensure we run it properly
            # Actually, telethon listener can just be an async function. Let's make it async.
            pass

        async def _async_on_message(display_name: str, msg) -> None:
            nonlocal match_count
            # Reverse-map display_name → channel_key for dedup/storage
            ch_key = next(
                (k for k, v in source_area_map.items() if v["title"] == display_name),
                display_name,
            )
            if is_seen(db_path, ch_key, msg.id):
                return
            mark_seen(db_path, ch_key, msg.id)

            areas_for_ch = source_area_map.get(ch_key, {}).get("areas", [])
            
            if ai_scorer:
                results = await ai_check_all_areas(areas_for_ch, msg.text, ai_scorer, ai_threshold)
            else:
                results = check_all_areas(areas_for_ch, msg.text)

            if not results:
                from telefeed.display import console
                console.print(f"  [dim]Skipped message from @{display_name} (no match)[/dim]")
                return

            for result in results:
                match_count += 1
                url = build_message_url(ch_key, msg.id)
                ts = msg.date.replace(tzinfo=None) if msg.date else None
                print_match(
                    area_name=result.area.name,
                    channel=display_name,
                    message_id=msg.id,
                    text=msg.text,
                    score=result.score,
                    matched_keywords=result.matched_keywords,
                    url=url,
                    timestamp=ts,
                    ai_reason=result.ai_reason,
                )
                if not no_save:
                    save_match(
                        db_path=db_path,
                        area=result.area.name,
                        channel=ch_key,
                        message_id=msg.id,
                        text=msg.text,
                        url=url,
                    )

        await client.listen_live(channel_pairs, _async_on_message)

    try:
        if live:
            asyncio.run(_run_live())
        else:
            asyncio.run(_run_fetch())
        
        if ai_scorer:
            print_info(ai_scorer.stats())

    except KeyboardInterrupt:
        print_info("Interrupted. Goodbye!")
    finally:
        asyncio.run(client.disconnect())


# ──────────────────────────────────────────────────────────────────────────────
# show-matches
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("show-matches")
@click.option("--area", default=None, help="Filter by area name")
@click.option("--status", default=None, type=click.Choice(["new", "saved", "archived"]), help="Filter by status")
@click.option("--limit", default=50, show_default=True, help="Max number of results to show")
def show_matches(area: Optional[str], status: Optional[str], limit: int) -> None:
    """Display previously saved matches from the local database."""
    db_path = os.getenv("DB_PATH", "telefeed.db")
    init_db(db_path)
    rows = get_matches(db_path, area=area, status=status, limit=limit)
    print_matches_table(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    cli()


if __name__ == "__main__":
    main()
