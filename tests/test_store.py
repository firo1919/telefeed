"""
Unit tests for telefeed.store module (SQLite persistence layer).
"""

from pathlib import Path
import pytest

from telefeed.store import (
    get_matches,
    init_db,
    is_seen,
    mark_seen,
    save_match,
    update_match_status,
)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "test_telefeed.db")
    init_db(path)
    return path


def test_init_db(db_path: str):
    # Running init_db twice should be idempotent
    init_db(db_path)
    assert Path(db_path).exists()


def test_seen_messages(db_path: str):
    channel = "remote_jobs"
    msg_id = 101

    assert is_seen(db_path, channel, msg_id) is False
    mark_seen(db_path, channel, msg_id)
    assert is_seen(db_path, channel, msg_id) is True

    # Duplicate mark_seen should be ignored without error
    mark_seen(db_path, channel, msg_id)
    assert is_seen(db_path, channel, msg_id) is True


def test_save_and_get_matches(db_path: str):
    save_match(
        db_path=db_path,
        area="Python Jobs",
        channel="pyjobs",
        message_id=1,
        text="Python backend role available.",
        url="https://t.me/pyjobs/1",
    )
    save_match(
        db_path=db_path,
        area="AI News",
        channel="ai_channel",
        message_id=2,
        text="New Gemini model released.",
        url="https://t.me/ai_channel/2",
    )

    all_matches = get_matches(db_path)
    assert len(all_matches) == 2

    python_matches = get_matches(db_path, area="Python Jobs")
    assert len(python_matches) == 1
    assert python_matches[0]["area"] == "Python Jobs"
    assert python_matches[0]["channel"] == "pyjobs"
    assert python_matches[0]["status"] == "new"

    new_status_matches = get_matches(db_path, status="new")
    assert len(new_status_matches) == 2


def test_duplicate_match_ignore(db_path: str):
    save_match(db_path, "Area1", "ch1", 10, "Text 1")
    save_match(db_path, "Area1", "ch1", 10, "Text 1 modified")

    matches = get_matches(db_path)
    assert len(matches) == 1
    assert matches[0]["text"] == "Text 1"  # Second save ignored by UNIQUE constraint


def test_update_match_status(db_path: str):
    save_match(db_path, "Area1", "ch1", 10, "Text 1")
    matches = get_matches(db_path)
    match_id = matches[0]["id"]

    update_match_status(db_path, match_id, "saved")
    updated = get_matches(db_path, status="saved")
    assert len(updated) == 1
    assert updated[0]["id"] == match_id

    update_match_status(db_path, match_id, "archived")
    archived = get_matches(db_path, status="archived")
    assert len(archived) == 1

    with pytest.raises(ValueError, match="Status must be one of"):
        update_match_status(db_path, match_id, "invalid_status")
