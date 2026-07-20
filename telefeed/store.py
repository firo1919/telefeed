"""
SQLite persistence layer.

Tables:
  - seen_messages   : tracks message IDs already processed per channel
  - matches         : stores messages that passed a filter, with metadata
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional


@contextmanager
def _conn(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(db_path: str) -> None:
    """Create tables if they don't already exist."""
    with _conn(db_path) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen_messages (
                channel     TEXT NOT NULL,
                message_id  INTEGER NOT NULL,
                PRIMARY KEY (channel, message_id)
            );

            CREATE TABLE IF NOT EXISTS matches (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                area        TEXT NOT NULL,
                channel     TEXT NOT NULL,
                message_id  INTEGER NOT NULL,
                text        TEXT NOT NULL,
                url         TEXT,
                matched_at  TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'new'
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_unique
                ON matches (channel, message_id, area);
            """
        )


def is_seen(db_path: str, channel: str, message_id: int) -> bool:
    """Return True if this (channel, message_id) has already been processed."""
    with _conn(db_path) as con:
        row = con.execute(
            "SELECT 1 FROM seen_messages WHERE channel=? AND message_id=?",
            (channel, message_id),
        ).fetchone()
    return row is not None


def mark_seen(db_path: str, channel: str, message_id: int) -> None:
    """Mark a message as seen so it won't be processed again."""
    with _conn(db_path) as con:
        con.execute(
            "INSERT OR IGNORE INTO seen_messages (channel, message_id) VALUES (?, ?)",
            (channel, message_id),
        )


def save_match(
    db_path: str,
    area: str,
    channel: str,
    message_id: int,
    text: str,
    url: Optional[str] = None,
) -> None:
    """Persist a matched message."""
    with _conn(db_path) as con:
        con.execute(
            """
            INSERT OR IGNORE INTO matches
                (area, channel, message_id, text, url, matched_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'new')
            """,
            (area, channel, message_id, text, url, datetime.utcnow().isoformat()),
        )


def get_matches(
    db_path: str,
    area: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[sqlite3.Row]:
    """Retrieve saved matches, optionally filtered by area and/or status."""
    query = "SELECT * FROM matches"
    params: list = []
    clauses: list[str] = []

    if area:
        clauses.append("area = ?")
        params.append(area)
    if status:
        clauses.append("status = ?")
        params.append(status)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY matched_at DESC LIMIT ?"
    params.append(limit)

    with _conn(db_path) as con:
        return con.execute(query, params).fetchall()


def update_match_status(db_path: str, match_id: int, new_status: str) -> None:
    """Update the status of a match (e.g., 'new' → 'saved' or 'archived')."""
    valid = {"new", "saved", "archived"}
    if new_status not in valid:
        raise ValueError(f"Status must be one of {valid}, got: {new_status!r}")
    with _conn(db_path) as con:
        con.execute("UPDATE matches SET status=? WHERE id=?", (new_status, match_id))
