"""
TeleFeed CLI entry point.

Commands:
  init          Create a fresh config.yaml file.
  doctor        Check configuration and test connectivity.
  auth          Log in to Telegram and save the session.
  fetch         Fetch recent messages from all configured sources and print matches.
  list-areas    Show all configured areas of concern.
  show-matches  Display previously saved matches from the local database.
  service       Manage background systemd service (install, start, stop, logs).
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import click
import yaml
from rich.progress import Progress, SpinnerColumn, TextColumn

from telefeed import __app_name__, __version__
from telefeed.ai_filter import build_scorer, ai_check_all_areas, BaseScorer
from telefeed.client import ChannelInfo, TeleFeedClient, build_message_url
from telefeed.config import (
    CONFIG_TEMPLATE,
    DEFAULT_CONFIG_PATH,
    TeleFeedConfig,
    load_telefeed_config,
)
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
from telefeed.filters import check_all_areas, load_areas_from_config
from telefeed.notifications import NotificationManager
from telefeed.service import (
    install_service,
    service_action,
    service_logs,
    uninstall_service,
)
from telefeed.store import (
    get_matches,
    init_db,
    is_seen,
    mark_seen,
    save_match,
)


def _validate_config(cfg: TeleFeedConfig) -> None:
    """Ensure essential Telegram API credentials are configured."""
    if not cfg.telegram.api_id or not cfg.telegram.api_hash or not cfg.telegram.phone:
        print_error(
            f"[bold]Telegram credentials are missing in {cfg.config_path}[/bold]\n\n"
            "  Please set your real Telegram API credentials under 'telegram:' in config.yaml:\n"
            "  1. Go to [link=https://my.telegram.org/apps]https://my.telegram.org/apps[/link]\n"
            "  2. Log in and click [bold]'API development tools'[/bold]\n"
            "  3. Fill in api_id, api_hash, and phone in config.yaml\n\n"
            "  Run [bold]telefeed init[/bold] to generate a config template."
        )
        raise SystemExit(1)

    if cfg.telegram.api_id == 12345678 or cfg.telegram.api_hash == "your_api_hash_here":
        print_error(
            f"[bold]{cfg.config_path} still contains placeholder credentials.[/bold]\n\n"
            "  Please edit config.yaml with your real Telegram credentials."
        )
        raise SystemExit(1)


# ──────────────────────────────────────────────────────────────────────────────
# CLI group
# ──────────────────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(__version__, prog_name=__app_name__)
def cli() -> None:
    """TeleFeed — Personalized Telegram feed aggregator."""
    print_banner()


# ──────────────────────────────────────────────────────────────────────────────
# init
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--local", is_flag=True, help="Create config.yaml in current directory instead of XDG path")
def init(local: bool) -> None:
    """Create a default config.yaml configuration file."""
    target_path = Path.cwd() / "config.yaml" if local else DEFAULT_CONFIG_PATH
    
    if target_path.exists():
        print_warning(f"Configuration file already exists at [bold]{target_path}[/bold]")
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as f:
        f.write(CONFIG_TEMPLATE)

    print_success(f"Created configuration file at [bold]{target_path}[/bold]")
    print_info("Edit this file to add your Telegram API credentials and custom Areas of Concern.")


# ──────────────────────────────────────────────────────────────────────────────
# doctor
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--config", default=None, help="Path to config.yaml")
def doctor(config: Optional[str]) -> None:
    """Check configuration validity and test notifications."""
    cfg = load_telefeed_config(config)
    print_section("TeleFeed Diagnostics")
    print_info(f"Config path : [bold]{cfg.config_path}[/bold] {'[green](found)[/green]' if cfg.config_path.exists() else '[red](missing)[/red]'}")
    print_info(f"Database path: [bold]{cfg.db_path}[/bold]")
    print_info(f"Session path : [bold]{cfg.session_path}[/bold]")
    print_info(f"Matcher mode : [bold]{cfg.matcher}[/bold] (threshold: {cfg.ai_threshold})")

    # Check Telegram credentials
    if cfg.telegram.api_id and cfg.telegram.api_hash:
        print_success("Telegram API credentials present.")
    else:
        print_error("Telegram API credentials missing in config.yaml.")

    if cfg.matcher == "ai":
        if cfg.ai.api_key:
            print_success(f"AI provider: [bold]{cfg.ai.provider}[/bold] / model: [bold]{cfg.ai.model}[/bold]")
        else:
            if cfg.ai.provider == "ollama":
                print_success("Ollama (local) configured — no API key required.")
            else:
                print_warning(f"AI provider '{cfg.ai.provider}' API key is missing in config.yaml.")

    # Notification checks
    print_section("Notification Drivers")
    print_info(f"Desktop OS notifications: {'[green]ENABLED[/green]' if cfg.notifications.desktop else '[dim]DISABLED[/dim]'}")
    
    bot_cfg = cfg.notifications.telegram_bot
    if bot_cfg.enabled:
        if bot_cfg.bot_token and bot_cfg.chat_id:
            print_success("Telegram Bot notifications configured.")
        else:
            print_warning("Telegram Bot notifications enabled but missing bot_token or chat_id.")
    else:
        print_info("Telegram Bot notifications: [dim]DISABLED[/dim]")


# ──────────────────────────────────────────────────────────────────────────────
# auth
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--config", default=None, help="Path to config.yaml")
def auth(config: Optional[str]) -> None:
    """Log in to Telegram and save your session."""
    cfg = load_telefeed_config(config)
    _validate_config(cfg)

    client = TeleFeedClient(
        session_file=str(cfg.session_path),
        api_id=cfg.telegram.api_id,
        api_hash=cfg.telegram.api_hash,
        phone=cfg.telegram.phone,
    )

    print_info(f"Session will be saved to [bold]{cfg.session_path}[/bold]")

    async def _run():
        await client.connect_and_auth()
        await client.disconnect()

    asyncio.run(_run())
    print_success("Authentication complete. You won't need to log in again.")


# ──────────────────────────────────────────────────────────────────────────────
# list-areas
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("list-areas")
@click.option("--config", default=None, help="Path to config.yaml")
def list_areas(config: Optional[str]) -> None:
    """Show all configured areas of concern."""
    cfg = load_telefeed_config(config)
    raw_dict = {"areas": cfg.areas}
    areas = load_areas_from_config(raw_dict)
    print_areas(areas)


# ──────────────────────────────────────────────────────────────────────────────
# fetch
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--config", default=None, help="Path to config.yaml")
@click.option("--limit", default=100, show_default=True, help="Max messages per channel per run")
@click.option("--live", is_flag=True, default=False, help="Keep running and watch for new messages")
@click.option("--area", default=None, help="Only run this specific area (by name)")
@click.option("--no-save", is_flag=True, default=False, help="Print matches but don't save to DB")
@click.option("--no-groups", is_flag=True, default=False, help="Exclude supergroups from auto-discovery")
@click.option("--backfill-days", default=7, show_default=True, help="In --live mode: days of history to scan on public channels before watching")
@click.option("--smart", is_flag=True, default=False, help="Force AI matching mode (overrides config.yaml)")
@click.option("--no-ai", is_flag=True, default=False, help="Force keyword matching mode (overrides config.yaml)")
@click.option("--notify", is_flag=True, default=False, help="Send desktop/bot notifications when matches are found")
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
    notify: bool,
) -> None:
    """Fetch messages from subscribed channels and print matches."""
    cfg = load_telefeed_config(config)
    _validate_config(cfg)

    raw_dict = {"areas": cfg.areas}
    all_areas = load_areas_from_config(raw_dict)

    if not all_areas:
        print_error("No areas configured. Add some to [bold]config.yaml[/bold] first.")
        raise SystemExit(1)

    if area:
        all_areas = [a for a in all_areas if a.name.lower() == area.lower()]
        if not all_areas:
            print_error(f"No area named [bold]{area!r}[/bold] found in config.")
            raise SystemExit(1)

    matcher = cfg.matcher
    if smart:
        matcher = "ai"
    if no_ai:
        matcher = "keywords"

    ai_scorer: BaseScorer | None = None
    if matcher == "ai":
        try:
            ai_scorer = build_scorer(
                provider=cfg.ai.provider,
                model=cfg.ai.model,
                api_key=cfg.ai.api_key,
                base_url=cfg.ai.base_url,
            )
            print_info(f"Using AI matching ({cfg.ai.provider} / {cfg.ai.model}) — threshold: {cfg.ai_threshold}")
        except (ValueError, ImportError) as e:
            print_error(str(e))
            raise SystemExit(1)
    else:
        print_info("Using Keyword matching")

    client = TeleFeedClient(
        session_file=str(cfg.session_path),
        api_id=cfg.telegram.api_id,
        api_hash=cfg.telegram.api_hash,
        phone=cfg.telegram.phone,
    )
    db_path = str(cfg.db_path)
    init_db(db_path)

    notifier = NotificationManager(cfg.notifications) if notify else None

    areas_watching_all = [a for a in all_areas if not a.sources]
    areas_with_sources = [a for a in all_areas if a.sources]

    async def _build_source_map() -> dict:
        source_map: dict[str, dict] = {}

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

    async def _run_fetch() -> None:
        nonlocal match_count, total_checked
        await client.connect_and_auth()
        source_area_map = await _build_source_map()

        if not source_area_map:
            print_warning("No channels to watch. Subscribe to channels or add sources to config.yaml.")
            return

        print_section(f"Scanning {len(source_area_map)} channel(s)")

        for channel_key, info in source_area_map.items():
            areas_for_channel = info["areas"]
            entity = info["entity"]
            title = info["title"]

            print_section(f"Fetching {title}")
            msg_count = 0
            channel_arg = entity if entity is not None else channel_key

            async for msg in client.fetch_messages(channel_arg, limit=limit):
                total_checked += 1
                msg_count += 1

                if is_seen(db_path, channel_key, msg.id):
                    continue
                mark_seen(db_path, channel_key, msg.id)

                if ai_scorer:
                    results = await ai_check_all_areas(areas_for_channel, msg.text, ai_scorer, cfg.ai_threshold)
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

                    if notifier:
                        await notifier.notify_match(
                            area_name=result.area.name,
                            channel_title=title,
                            text=msg.text,
                            score=result.score,
                            url=url,
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
            print_warning("No matches found. Try adjusting your keywords in config.yaml.")
        else:
            print_success(f"Found [bold]{match_count}[/bold] match(es) from {total_checked} message(s) checked.")

    async def _run_live() -> None:
        nonlocal match_count
        await client.connect_and_auth()
        source_area_map = await _build_source_map()

        if not source_area_map:
            print_warning("No channels to watch. Subscribe to channels or add sources to config.yaml.")
            return

        if notifier:
            await notifier.notify_startup(len(source_area_map), len(all_areas))

        backfill_cutoff = datetime.now(timezone.utc) - timedelta(days=backfill_days)
        backfill_total = 0
        backfill_matches = 0

        print_section(
            f"Backfilling {len(source_area_map)} channel(s) "
            f"(channels: {backfill_days}d history | groups: unread only)"
        )

        for channel_key, info in source_area_map.items():
            areas_for_channel = info["areas"]
            entity = info["entity"]
            title = info["title"]
            is_broadcast = info.get("is_broadcast", False)
            unread = info.get("unread_count", 0)

            channel_arg = entity if entity is not None else channel_key

            if is_broadcast:
                fetch_kwargs = dict(limit=None, min_date=backfill_cutoff)
                scope_label = f"{backfill_days}d history"
            elif unread > 0:
                fetch_kwargs = dict(limit=min(unread, 500))
                scope_label = f"{unread} unread"
            else:
                continue

            msg_count = 0
            async for msg in client.fetch_messages(channel_arg, **fetch_kwargs):
                backfill_total += 1
                msg_count += 1

                if is_seen(db_path, channel_key, msg.id):
                    continue
                mark_seen(db_path, channel_key, msg.id)

                if ai_scorer:
                    results = await ai_check_all_areas(areas_for_channel, msg.text, ai_scorer, cfg.ai_threshold)
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
                    if notifier:
                        await notifier.notify_match(
                            area_name=result.area.name,
                            channel_title=title,
                            text=msg.text,
                            score=result.score,
                            url=url,
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

        channel_pairs = [
            (info["title"], info["entity"] if info["entity"] is not None else ch_key)
            for ch_key, info in source_area_map.items()
        ]

        async def _async_on_message(display_name: str, msg) -> None:
            nonlocal match_count
            ch_key = next(
                (k for k, v in source_area_map.items() if v["title"] == display_name),
                display_name,
            )
            if is_seen(db_path, ch_key, msg.id):
                return
            mark_seen(db_path, ch_key, msg.id)

            areas_for_ch = source_area_map.get(ch_key, {}).get("areas", [])
            
            if ai_scorer:
                results = await ai_check_all_areas(areas_for_ch, msg.text, ai_scorer, cfg.ai_threshold)
            else:
                results = check_all_areas(areas_for_ch, msg.text)

            if not results:
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
                if notifier:
                    await notifier.notify_match(
                        area_name=result.area.name,
                        channel_title=display_name,
                        text=msg.text,
                        score=result.score,
                        url=url,
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
@click.option("--config", default=None, help="Path to config.yaml")
@click.option("--area", default=None, help="Filter by area name")
@click.option("--status", default=None, type=click.Choice(["new", "saved", "archived"]), help="Filter by status")
@click.option("--limit", default=50, show_default=True, help="Max number of results to show")
def show_matches(config: Optional[str], area: Optional[str], status: Optional[str], limit: int) -> None:
    """Display previously saved matches from the local database."""
    cfg = load_telefeed_config(config)
    db_path = str(cfg.db_path)
    init_db(db_path)
    rows = get_matches(db_path, area=area, status=status, limit=limit)
    print_matches_table(rows)


# ──────────────────────────────────────────────────────────────────────────────
# service command group
# ──────────────────────────────────────────────────────────────────────────────

@cli.group()
def service() -> None:
    """Manage background systemd service."""
    pass


@service.command("install")
def service_install_cmd() -> None:
    """Install and enable the background systemd user service."""
    install_service()


@service.command("uninstall")
def service_uninstall_cmd() -> None:
    """Disable and remove the background systemd user service."""
    uninstall_service()


@service.command("start")
def service_start_cmd() -> None:
    """Start the background service."""
    service_action("start")


@service.command("stop")
def service_stop_cmd() -> None:
    """Stop the background service."""
    service_action("stop")


@service.command("restart")
def service_restart_cmd() -> None:
    """Restart the background service."""
    service_action("restart")


@service.command("status")
def service_status_cmd() -> None:
    """View the background service status."""
    service_action("status")


@service.command("logs")
def service_logs_cmd() -> None:
    """Stream live background service logs."""
    service_logs()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    cli()


if __name__ == "__main__":
    main()
