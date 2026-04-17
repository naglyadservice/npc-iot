import asyncio
import json

import pytest

from npc_iot.base.client import BaseClient
from npc_iot.exception import DeviceResponseError
from npc_iot.npc.client import NpcClient


async def _fixed_request_id():
    return 1000


@pytest.fixture
def base_client(mock_connector):
    return BaseClient(
        connector=mock_connector,
        topic_prefix="test",
        request_id_generator=_fixed_request_id,
    )


@pytest.fixture
def npc_client(mock_connector):
    return NpcClient(
        connector=mock_connector,
        request_id_generator=_fixed_request_id,
    )


async def test_send_and_receive_response(base_client):
    waiter = await base_client.send_message(
        topic_template="/{device_id}/client/reboot/set",
        path_params={"device_id": "DEV1"},
        qos=1,
        payload={"delay": 10},
    )

    await base_client._result_callback({"request_id": waiter.request_id, "code": 0, "data": "ok"})
    result = await waiter.wait(timeout=1)
    assert result["data"] == "ok"


async def test_send_and_receive_error(base_client):
    waiter = await base_client.send_message(
        topic_template="/{device_id}/client/reboot/set",
        path_params={"device_id": "DEV1"},
        qos=1,
        payload={"delay": 10},
    )

    await base_client._result_callback({"request_id": waiter.request_id, "code": 5})
    with pytest.raises(DeviceResponseError) as exc_info:
        await waiter.wait(timeout=1)
    assert exc_info.value.code == 5


async def test_waiter_timeout_cleans_up(base_client):
    waiter = await base_client.send_message(
        topic_template="/{device_id}/client/reboot/set",
        path_params={"device_id": "DEV1"},
        qos=1,
        payload={},
        request_id=555,
    )

    with pytest.raises(asyncio.TimeoutError):
        await waiter.wait(timeout=0.05)

    waiter2 = await base_client.send_message(
        topic_template="/{device_id}/client/reboot/set",
        path_params={"device_id": "DEV1"},
        qos=1,
        payload={},
        request_id=555,
    )
    await base_client._result_callback({"request_id": 555, "code": 0})
    result = await waiter2.wait(timeout=1)
    assert result["request_id"] == 555


async def test_request_id_injected_to_payload(base_client, mock_connector):
    await base_client.send_message(
        topic_template="/{device_id}/client/state/set",
        path_params={"device_id": "DEV1"},
        qos=1,
        payload={"relay": []},
    )

    sent = mock_connector.sent_messages[0]
    decoded = json.loads(sent["payload"])
    assert "request_id" in decoded
    assert decoded["request_id"] == 1000
    assert decoded["relay"] == []
    assert sent["topic"] == "test/DEV1/client/state/set"


@pytest.mark.parametrize(
    "method,kwargs,expected_topic_suffix,expected_qos",
    [
        ("reboot", {"payload": {"delay": 1}}, "/client/reboot/set", 1),
        ("set_state", {"payload": {"relay": []}}, "/client/state/set", 2),
        ("get_state", {"payload": {"relay": []}}, "/client/state/get", 1),
        ("add_phones", {"payload": {"phones": ["+380"]}}, "/client/phone/add_multi", 1),
        ("del_phones", {"payload": {"phones": ["+380"]}}, "/client/phone/del", 1),
    ],
)
async def test_npc_methods_produce_correct_topics(
    npc_client, mock_connector, method, kwargs, expected_topic_suffix, expected_qos
):
    await getattr(npc_client, method)(device_id="DEV1", **kwargs)

    sent = mock_connector.sent_messages[0]
    assert sent["topic"] == f"v2/DEV1{expected_topic_suffix}"
    assert sent["qos"] == expected_qos


async def test_npc_custom_prefix(mock_connector):
    client = NpcClient(
        connector=mock_connector,
        topic_prefix="custom",
        request_id_generator=_fixed_request_id,
    )
    await client.reboot(device_id="DEV1", payload={"delay": 1})

    sent = mock_connector.sent_messages[0]
    assert sent["topic"] == "custom/DEV1/client/reboot/set"
