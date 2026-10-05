"""keep_alive доходить до клієнта mqttproto: без нього брокер не прибирає сесію
зупиненого процесу ніколи (keep_alive 0 = сесія вічна)."""

import asyncio
from unittest.mock import patch

import pytest

from npc_iot.base.client import BaseClient
from npc_iot.connectors.mqttproto_connector import MqttprotoConnector

from .test_connector import _make_mock_mqtt_client


def _recording_client():
    base = _make_mock_mqtt_client()
    created: list[dict] = []

    class Recording(base):
        def __init__(self, **kwargs):
            created.append(kwargs)
            super().__init__(**kwargs)

    return Recording, created


async def _connect_kwargs(connector: MqttprotoConnector) -> dict:
    client_cls, created = _recording_client()
    with (
        patch("npc_iot.connectors.mqttproto_connector.AsyncMQTTClient", client_cls),
        patch.object(connector, "_verify_subscriptions_work", return_value=True),
    ):
        async with connector:
            await asyncio.sleep(0.05)
    assert created, "connector never created an mqttproto client"
    return created[0]


async def test_connector_passes_keep_alive_to_mqttproto():
    connector = MqttprotoConnector(host="localhost", port=1883, keep_alive=60)

    assert (await _connect_kwargs(connector))["keep_alive"] == 60


async def test_connector_default_keep_alive_stays_zero():
    connector = MqttprotoConnector(host="localhost", port=1883)

    assert (await _connect_kwargs(connector))["keep_alive"] == 0


async def test_base_client_forwards_keep_alive_to_its_connector():
    client = BaseClient(host="localhost", port=1883, keep_alive=60)

    assert (await _connect_kwargs(client._connector))["keep_alive"] == 60


def test_keep_alive_with_explicit_connector_is_rejected():
    connector = MqttprotoConnector(host="localhost", port=1883)

    with pytest.raises(ValueError):
        BaseClient(connector=connector, keep_alive=60)


def test_pinned_mqttproto_accepts_the_connector_config():
    """Охоронець піна: mqttproto без keep_alive упав би тут TypeError, а не в проді."""
    from mqttproto.async_client import AsyncMQTTClient

    connector = MqttprotoConnector(host="localhost", port=1883, clean_start=True, keep_alive=60)

    assert AsyncMQTTClient(**connector._client_config).keep_alive == 60
