import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from npc_iot.base.dispatcher import BaseDispatcher, MessageHandler
from npc_iot.npc.dispatcher import NpcDispatcher


async def test_topic_pattern_matching(mock_connector):
    handler = MessageHandler("/{device_id}/server/begin")
    received = {}

    async def cb(device_id: str, payload):
        received["device_id"] = device_id
        received["payload"] = payload

    handler.register_callback(cb)

    async with handler.handle_messages(
        connector=mock_connector,
        topic_prefix="v2",
        payload_decoder=json.loads,
        ctx=None,
    ):
        await mock_connector.inject_message("v2/ABC123/server/begin", b'{"ok": true}')
        await asyncio.sleep(0.05)

    assert received["device_id"] == "ABC123"
    assert received["payload"] == {"ok": True}


async def test_multi_path_vars(mock_connector):
    handler = MessageHandler("/{device_id}/server/{action}")
    received = {}

    async def cb(device_id: str, action: str, payload):
        received["device_id"] = device_id
        received["action"] = action

    handler.register_callback(cb)

    async with handler.handle_messages(
        connector=mock_connector,
        topic_prefix="",
        payload_decoder=json.loads,
        ctx=None,
    ):
        await mock_connector.inject_message("/DEV1/server/reboot", b'{}')
        await asyncio.sleep(0.05)

    assert received == {"device_id": "DEV1", "action": "reboot"}


async def test_callback_signature_validation_unknown_arg():
    handler = MessageHandler("/{device_id}/server/begin")

    async def cb(device_id: str, unknown_required):
        pass

    with pytest.raises(TypeError, match="unknown_required"):
        handler.register_callback(cb)


async def test_wrong_type_annotation():
    handler = MessageHandler("/{device_id}/server/begin")

    async def cb(device_id: int):
        pass

    with pytest.raises(TypeError, match="Type mismatch"):
        handler.register_callback(cb)


async def test_payload_decode_error_doesnt_crash(mock_connector):
    handler = MessageHandler("/{device_id}/server/begin")
    cb_called = False

    async def cb(device_id: str, payload):
        nonlocal cb_called
        cb_called = True

    handler.register_callback(cb)

    def bad_decoder(data):
        raise ValueError("broken")

    async with handler.handle_messages(
        connector=mock_connector,
        topic_prefix="v2",
        payload_decoder=bad_decoder,
        ctx=None,
    ):
        await mock_connector.inject_message("v2/DEV1/server/begin", b"garbage")
        await asyncio.sleep(0.05)

    assert not cb_called


async def test_dispatcher_subscribes_all_handlers(mock_connector):
    dispatcher = NpcDispatcher()

    async def cb(payload, **kwargs):
        pass

    dispatcher.register_callbacks(cb)

    async with dispatcher.start_handling(
        connector=mock_connector,
        topic_prefix="v2",
        payload_decoder=json.loads,
    ):
        subscribed_topics = set(mock_connector._subscriptions.keys())

    assert "v2/+/server/begin" in subscribed_topics
    assert "v2/+/server/reboot/ack" in subscribed_topics
    assert "v2/+/server/state" in subscribed_topics
    assert "v2/+/server/state/info" in subscribed_topics
    assert "v2/+/phone/add_multi/ack" in subscribed_topics


async def test_topic_with_regex_metacharacters(mock_connector):
    """$SYS topics are not a special case for MQTT, but "$" is for a regex: unescaped,
    it anchors to end-of-string and the handler never recognises its own messages."""
    handler = MessageHandler("$SYS/brokers/{broker}/clients/{device_id}/connected")
    received = {}

    async def cb(device_id: str, broker: str, payload):
        received["device_id"] = device_id
        received["broker"] = broker

    handler.register_callback(cb)

    assert handler.mqtt_sub_topic == "$SYS/brokers/+/clients/+/connected"

    async with handler.handle_messages(
        connector=mock_connector,
        topic_prefix="",
        payload_decoder=json.loads,
        ctx=None,
    ):
        await mock_connector.inject_message(
            "$SYS/brokers/emqx@1/clients/DEV1/connected", b"{}"
        )
        await asyncio.sleep(0.05)

    assert received == {"device_id": "DEV1", "broker": "emqx@1"}
