import asyncio
from unittest.mock import Mock

import pytest

from npc_iot.exception import DeviceResponseError
from npc_iot.response import ResponseWaiter, _default_request_id_generator


def _make_waiter(request_id=42, cancel_callback=None):
    return ResponseWaiter(
        device_id="DEVICE1",
        request_id=request_id,
        ttl=5,
        cancel_callback=cancel_callback,
    )


async def test_successful_response():
    waiter = _make_waiter()
    waiter._set_result({"request_id": 42, "status": "ok"})
    result = await waiter.wait(timeout=1)
    assert result == {"request_id": 42, "status": "ok"}


async def test_error_response():
    waiter = _make_waiter()
    waiter._set_exception(DeviceResponseError(5))
    with pytest.raises(DeviceResponseError) as exc_info:
        await waiter.wait(timeout=1)
    assert exc_info.value.code == 5


async def test_timeout():
    waiter = _make_waiter()
    with pytest.raises(asyncio.TimeoutError):
        await waiter.wait(timeout=0.05)


async def test_timeout_fires_cancel_callback():
    cb = Mock()
    waiter = _make_waiter(request_id=99, cancel_callback=cb)
    with pytest.raises(asyncio.TimeoutError):
        await waiter.wait(timeout=0.05)
    cb.assert_called_once_with(99)


async def test_double_result_no_crash():
    waiter = _make_waiter()
    waiter._set_result({"first": True})
    waiter._set_result({"second": True})
    result = await waiter.wait(timeout=1)
    assert result == {"first": True}


async def test_default_request_id_generator():
    rid = await _default_request_id_generator()
    assert isinstance(rid, int)
    assert 0 <= rid <= 0xFFFF
