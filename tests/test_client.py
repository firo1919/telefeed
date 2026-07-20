"""
Unit tests for telefeed.client module (Telethon client wrapper & channel info helpers).
"""

from unittest.mock import AsyncMock, patch

from telefeed.client import ChannelInfo, TeleFeedClient, build_message_url


def test_channel_info_dataclass():
    info = ChannelInfo(
        key="pyjobs",
        title="Python Jobs Channel",
        entity=None,
        unread_count=5,
        is_broadcast=True,
    )
    assert info.key == "pyjobs"
    assert info.title == "Python Jobs Channel"
    assert info.unread_count == 5
    assert info.is_broadcast is True


def test_build_message_url():
    url = build_message_url("devjobs", 1234)
    assert url == "https://t.me/devjobs/1234"


def test_telefeed_client_init():
    client = TeleFeedClient("test.session", 12345, "hash_str", "+123456789")
    assert client.phone == "+123456789"
