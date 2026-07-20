"""
Rich-powered terminal display helpers.
All output in TeleFeed goes through this module for a consistent look.
"""

from datetime import datetime
from typing import Optional

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

console = Console()


# ──────────────────────────────────────────────────────────────────────────────
# App Banner
# ──────────────────────────────────────────────────────────────────────────────

BANNER = r"""
  ████████╗███████╗██╗     ███████╗    ███████╗███████╗███████╗██████╗
     ██╔══╝██╔════╝██║     ██╔════╝    ██╔════╝██╔════╝██╔════╝██╔══██╗
     ██║   █████╗  ██║     █████╗      █████╗  █████╗  █████╗  ██║  ██║
     ██║   ██╔══╝  ██║     ██╔══╝      ██╔══╝  ██╔══╝  ██╔══╝  ██║  ██║
     ██║   ███████╗███████╗███████╗    ██║     ███████╗███████╗██████╔╝
     ╚═╝   ╚══════╝╚══════╝╚══════╝    ╚═╝     ╚══════╝╚══════╝╚═════╝
"""

SUBTITLE = "  📡  Personalized Telegram Feed — v0.1.0"


def print_banner() -> None:
    console.print(f"[bold cyan]{BANNER}[/bold cyan]")
    console.print(f"[dim]{SUBTITLE}[/dim]\n")


# ──────────────────────────────────────────────────────────────────────────────
# Match cards
# ──────────────────────────────────────────────────────────────────────────────

def print_match(
    area_name: str,
    channel: str,
    message_id: int,
    text: str,
    score: float,
    matched_keywords: list[str],
    url: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    ai_reason: Optional[str] = None,
) -> None:
    """Print a single matched message as a Rich Panel."""
    # Score bar (10 chars wide)
    filled = round(score * 10)
    bar = "█" * filled + "░" * (10 - filled)
    score_str = f"[green]{bar}[/green] {score:.0%}"

    # Header line
    ts_str = f"  [dim]{timestamp.strftime('%Y-%m-%d %H:%M')}[/dim]" if timestamp else ""
    # Channel display: omit @ for private channels stored as "id:NNNN"
    ch_display = channel if channel.startswith("id:") else f"@{channel}"
    header = (
        f"[bold magenta]{area_name}[/bold magenta]  │  "
        f"[cyan]{ch_display}[/cyan]  [dim]#{message_id}[/dim]{ts_str}"
    )

    # Body — truncate very long messages
    body_text = text.strip()
    if len(body_text) > 800:
        body_text = body_text[:800] + " [dim]…[/dim]"

    # Keyword badge row
    kw_badges = "  ".join(
        f"[black on yellow] {kw} [/black on yellow]" for kw in matched_keywords
    )

    footer_parts = [f"Relevance: {score_str}"]
    if matched_keywords:
        footer_parts.append(f"Matched: {kw_badges}")
    if url:
        footer_parts.append(f"[link={url}][blue]Open in Telegram ↗[/blue][/link]")

    footer = "   ".join(footer_parts)

    # AI reason line (shown only in AI mode)
    ai_line = ""
    if ai_reason:
        ai_line = f"\n[bold cyan]🤖 AI:[/bold cyan] [italic dim]{ai_reason}[/italic dim]"

    panel_content = f"{body_text}\n\n{footer}{ai_line}"

    console.print(
        Panel(
            panel_content,
            title=header,
            border_style="bright_blue",
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# Saved matches table
# ──────────────────────────────────────────────────────────────────────────────

def print_matches_table(rows: list) -> None:
    """Print saved matches from the DB as a Rich table."""
    if not rows:
        console.print("[yellow]No saved matches found.[/yellow]")
        return

    table = Table(
        title="Saved Matches",
        box=box.ROUNDED,
        border_style="bright_blue",
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Area", style="magenta", min_width=14)
    table.add_column("Channel", style="cyan", min_width=12)
    table.add_column("Preview", min_width=40, max_width=70)
    table.add_column("Status", min_width=8)
    table.add_column("Matched At", style="dim", min_width=16)

    status_colors = {"new": "green", "saved": "yellow", "archived": "dim"}

    for row in rows:
        preview = row["text"].strip().replace("\n", " ")[:120]
        if len(row["text"]) > 120:
            preview += "…"
        color = status_colors.get(row["status"], "white")
        table.add_row(
            str(row["id"]),
            row["area"],
            f"@{row['channel']}",
            preview,
            f"[{color}]{row['status']}[/{color}]",
            row["matched_at"][:16],
        )

    console.print(table)


# ──────────────────────────────────────────────────────────────────────────────
# Areas config summary
# ──────────────────────────────────────────────────────────────────────────────

def print_areas(areas: list) -> None:
    """Print a summary of all configured areas of concern."""
    if not areas:
        console.print("[yellow]No areas configured. Edit config.yaml to get started.[/yellow]")
        return

    console.print(Rule("[bold cyan]Areas of Concern[/bold cyan]"))
    for area in areas:
        kw_list = ", ".join(f"[yellow]{k}[/yellow]" for k in area.keywords) or "[dim]none[/dim]"
        neg_list = ", ".join(f"[red]{k}[/red]" for k in area.negative_keywords) or "[dim]none[/dim]"
        src_list = ", ".join(f"[cyan]@{s}[/cyan]" for s in area.sources) or "[dim]none[/dim]"

        desc = area.description.strip()[:200]

        content = (
            f"[bold]Description:[/bold] [dim]{desc}[/dim]\n\n"
            f"[bold]Keywords:[/bold] {kw_list}\n"
            f"[bold]Negative:[/bold] {neg_list}\n"
            f"[bold]Sources:[/bold]  {src_list}"
        )
        console.print(
            Panel(
                content,
                title=f"[bold magenta]{area.name}[/bold magenta]",
                border_style="bright_blue",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )


# ──────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ──────────────────────────────────────────────────────────────────────────────

def print_section(title: str) -> None:
    console.print(Rule(f"[bold]{title}[/bold]"))


def print_success(msg: str) -> None:
    console.print(f"[bold green]✔[/bold green]  {msg}")


def print_error(msg: str) -> None:
    console.print(f"[bold red]✖[/bold red]  {msg}")


def print_info(msg: str) -> None:
    console.print(f"[bold blue]ℹ[/bold blue]  {msg}")


def print_warning(msg: str) -> None:
    console.print(f"[bold yellow]⚠[/bold yellow]  {msg}")
