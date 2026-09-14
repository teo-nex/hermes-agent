"""Slack lifecycle notices must not become agent turns (regression for #110778)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import PlatformConfig
from plugins.platforms.slack.adapter import SlackAdapter


@pytest.fixture
def adapter():
    instance = SlackAdapter(PlatformConfig(
        enabled=True,
        token="xoxb-test",
        extra={"free_response_channels": ["C_TEST"], "allow_bots": "all"},
    ))
    instance._bot_user_id = "U_BOT"
    instance._running = True
    instance._app = SimpleNamespace(client=SimpleNamespace(
        users_info=AsyncMock(return_value={
            "ok": True, "user": {"is_bot": False, "real_name": "Test User"},
        }),
        conversations_info=AsyncMock(return_value={
            "ok": True, "channel": {"name": "test"},
        }),
        conversations_replies=AsyncMock(return_value={"ok": True, "messages": []}),
    ))
    instance.handle_message = AsyncMock()
    return instance


def _event(subtype, *, edited=False):
    message = {
        "type": "message", "user": "U_TEST", "text": "A message",
        "channel": "C_TEST", "channel_type": "channel",
        "team": "T_TEST", "ts": "100.000001",
    }
    if subtype is not None:
        message["subtype"] = subtype
    if subtype == "thread_broadcast":
        message["thread_ts"] = "99.000001"
    if subtype == "bot_message":
        message["bot_id"] = "B_OTHER"
    if subtype == "document_mention":
        message["type"] = "app_mention"
    if not edited:
        return message
    return {
        "type": "message", "subtype": "message_changed",
        "channel": "C_TEST", "channel_type": "channel", "team": "T_TEST",
        "ts": "101.000001", "event_ts": "101.000001", "message": message,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("edited", [False, True], ids=["original", "edited"])
@pytest.mark.parametrize(("subtype", "conversational"), [
    (None, True),
    ("", True),
    ("file_share", True),
    ("file_mention", True),
    ("file_comment", True),
    ("me_message", True),
    ("thread_broadcast", True),
    ("reply_broadcast", True),
    ("document_mention", True),
    ("bot_message", True),
    ("channel_convert_to_private", False),
    ("channel_convert_to_public", False),
    ("channel_join", False),
    ("channel_leave", False),
    ("channel_name", False),
    ("channel_topic", False),
    ("channel_purpose", False),
    ("channel_archive", False),
    ("channel_unarchive", False),
    ("channel_posting_permissions", False),
    ("group_join", False),
    ("group_leave", False),
    ("group_name", False),
    ("group_topic", False),
    ("group_purpose", False),
    ("group_archive", False),
    ("group_unarchive", False),
    ("pinned_item", False),
    ("unpinned_item", False),
    ("message_deleted", False),
    ("message_replied", False),
    ("assistant_app_thread", False),
    ("reminder_add", False),
    ("ekm_access_denied", False),
    ("future_lifecycle_notice", False),
])
async def test_only_conversational_messages_reach_the_agent(adapter, subtype, conversational, edited):
    await adapter._handle_slack_message(_event(subtype, edited=edited))

    if conversational:
        adapter.handle_message.assert_awaited_once()
        delivered = adapter.handle_message.await_args.args[0]
        assert delivered.text == "A message"
        assert delivered.source.user_id == "U_TEST"
    else:
        adapter.handle_message.assert_not_awaited()
        adapter._app.client.users_info.assert_not_awaited()
        adapter._app.client.conversations_info.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("policy", "mentioned", "accepted"), [
    ("none", False, False),
    ("none", True, False),
    ("mentions", False, False),
    ("mentions", True, True),
    ("all", False, True),
])
async def test_conversational_bot_posts_still_obey_allow_bots(adapter, policy, mentioned, accepted):
    adapter.config.extra["allow_bots"] = policy
    event = _event("bot_message")
    if mentioned:
        event["text"] = "<@U_BOT> A message"

    await adapter._handle_slack_message(event)

    assert adapter.handle_message.await_count == int(accepted)
