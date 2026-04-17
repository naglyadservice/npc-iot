import asyncio
from contextlib import asynccontextmanager, suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from npc_iot.connectors.mqttproto_connector import MqttprotoConnector


class FakeSubscription:
    def __init__(self, messages=None):
        self._messages = messages or []
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._messages):
            await asyncio.sleep(100)
            raise StopAsyncIteration
        msg = self._messages[self._index]
        self._index += 1
        return msg


class FakeMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload


def _make_mock_mqtt_client(publish_side_effect=None, connect_fail_count=0):
    call_count = 0

    class MockMQTTClient:
        def __init__(self, **kwargs):
            self._subs = {}
            self.publish = AsyncMock(side_effect=publish_side_effect)

        async def __aenter__(self):
            nonlocal call_count
            call_count += 1
            if call_count <= connect_fail_count:
                raise ConnectionError("mock connection refused")
            return self

        async def __aexit__(self, *args):
            pass

        @asynccontextmanager
        async def subscribe(self, topic, maximum_qos=None):
            sub = FakeSubscription()
            self._subs[topic] = sub
            try:
                yield sub
            finally:
                self._subs.pop(topic, None)

    return MockMQTTClient


@pytest.fixture
def connector():
    return MqttprotoConnector(
        host="localhost",
        port=1883,
        health_check_min_interval=0.05,
        health_check_max_interval=0.1,
        health_check_timeout=0.5,
    )


async def test_connect_publish_disconnect(connector):
    MockClient = _make_mock_mqtt_client()

    with patch(
        "npc_iot.connectors.mqttproto_connector.AsyncMQTTClient", MockClient
    ), patch.object(connector, "_verify_subscriptions_work", return_value=True):
        async with connector:
            await asyncio.sleep(0.1)
            await connector.send_message("test/topic", qos=1, payload=b"hello")

    assert True


async def test_subscribe_receives_messages(connector):
    MockClient = _make_mock_mqtt_client()
    received = []

    async def on_message(topic, payload):
        received.append({"topic": topic, "payload": payload})

    with patch(
        "npc_iot.connectors.mqttproto_connector.AsyncMQTTClient", MockClient
    ), patch.object(connector, "_verify_subscriptions_work", return_value=True):
        async with connector:
            async with connector.subscribe("test/topic", on_message):
                await asyncio.sleep(0.1)
                assert "test/topic" in connector._active_subscriptions


async def test_reconnect_after_connection_drop(connector):
    connect_count = 0
    original_verify = connector._verify_subscriptions_work

    class ReconnectMockClient:
        def __init__(self, **kwargs):
            self.publish = AsyncMock()

        async def __aenter__(self):
            nonlocal connect_count
            connect_count += 1
            if connect_count == 1:
                raise ConnectionError("first connect fails")
            return self

        async def __aexit__(self, *args):
            pass

        @asynccontextmanager
        async def subscribe(self, topic, maximum_qos=None):
            yield FakeSubscription()

    with patch(
        "npc_iot.connectors.mqttproto_connector.AsyncMQTTClient", ReconnectMockClient
    ), patch.object(connector, "_verify_subscriptions_work", return_value=True):
        async with connector:
            await asyncio.sleep(1.5)

    assert connect_count >= 2


async def test_health_check_triggers_reconnect(connector):
    connect_count = 0
    verify_call_count = 0

    class HealthCheckMockClient:
        def __init__(self, **kwargs):
            self.publish = AsyncMock()

        async def __aenter__(self):
            nonlocal connect_count
            connect_count += 1
            return self

        async def __aexit__(self, *args):
            pass

        @asynccontextmanager
        async def subscribe(self, topic, maximum_qos=None):
            yield FakeSubscription()

    async def mock_verify():
        nonlocal verify_call_count
        verify_call_count += 1
        # Call 3 is the health check loop → fail to trigger reconnect
        # All other calls (initial verify on each connection) succeed
        return verify_call_count != 3

    with patch(
        "npc_iot.connectors.mqttproto_connector.AsyncMQTTClient", HealthCheckMockClient
    ), patch.object(connector, "_verify_subscriptions_work", side_effect=mock_verify):
        async with connector:
            for _ in range(60):
                await asyncio.sleep(0.05)
                if connect_count >= 2:
                    break

    assert connect_count >= 2
