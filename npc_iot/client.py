import logging
import secrets
from contextlib import AsyncExitStack
from typing import Any, Callable, Generic, Literal, Mapping, Protocol, Self, TypeVar

try:
    import orjson as json
except ImportError:
    import json

try:
    from mqttproto.async_client import AsyncMQTTClient
except ImportError:
    AsyncMQTTClient = None

from .connectors.base import BaseConnector
from .connectors.mqttproto_connector import MqttprotoConnector
from .dispatcher import Dispatcher
from .exception import DeviceResponceError
from .response import ResponseWaiter
from .types import (
    AckResponse,
    BaseResponse,
    GetStatePayload,
    GetStateResponse,
    RebootPayload,
    SetStatePayload,
)

log = logging.getLogger(__name__)


async def _defult_request_id_generator() -> int:
    return secrets.randbits(16)


class RequestIdGenerator(Protocol):
    async def __call__(self) -> int: ...


ResponseWaiterType = TypeVar("ResponseWaiterType", bound=BaseResponse)

DispatcherType = TypeVar("DispatcherType", bound=Dispatcher)


class NpcClient(Generic[DispatcherType]):
    def __init__(
        self,
        connector: BaseConnector | None = None,
        host: str | None = None,
        port: int | None = None,
        ssl: bool | None = None,
        client_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
        clean_start: bool | None = None,
        topic_prefix: str = "v2/",
        payload_encoder: Callable[[Any], str | bytes] = json.dumps,
        payload_decoder: Callable[[str | bytes], Any] = json.loads,
        request_id_generator: RequestIdGenerator = _defult_request_id_generator,
        dispatcher: DispatcherType | None = None,
    ) -> None:
        if connector is not None and any(
            (host, port, ssl, client_id, username, password, clean_start)
        ):
            raise ValueError("connector and other connection parameters cannot be passed together")

        if connector is None:
            if AsyncMQTTClient is None:
                raise ImportError("mqttproto is not installed")

            if host is None:
                raise ValueError("host is required, when connector not passed")

            if port is None:
                raise ValueError("port is required, when connector not passed")

            if ssl is None:
                ssl = False

            if clean_start is None:
                clean_start = True

            connector = MqttprotoConnector(
                mqtt_client=AsyncMQTTClient(
                    host_or_path=host,
                    port=port,
                    ssl=ssl,
                    client_id=client_id,
                    username=username,
                    password=password,
                    clean_start=clean_start,
                )
            )

        self._connector = connector
        self._topic_prefix = topic_prefix
        self._request_id_generator = request_id_generator
        self._response_waiters: dict[int, ResponseWaiter] = {}
        self._payload_encoder = payload_encoder
        self._payload_decoder = payload_decoder

        if dispatcher is None:
            self.dispatcher = Dispatcher()
        else:
            self.dispatcher = dispatcher

        self.dispatcher.register_callbacks(self._result_callback)

    async def __aenter__(self) -> Self:
        async with AsyncExitStack() as exit_stack:
            await exit_stack.enter_async_context(self._connector)
            await exit_stack.enter_async_context(
                self.dispatcher.start_handling(
                    connector=self._connector,
                    topic_prefix=self._topic_prefix,
                    payload_decoder=self._payload_decoder,
                )
            )
            self._exit_stack = exit_stack.pop_all()

        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self._exit_stack.__aexit__(None, None, None)

    async def _send_message(
        self,
        device_id: str,
        topic: str,
        qos: Literal[0, 1, 2],
        payload: Mapping[str, Any] | None,
        ttl: int | None,
    ) -> ResponseWaiter:
        response_waiter = ResponseWaiter(
            device_id=device_id,
            request_id=await self._request_id_generator(),
            ttl=ttl,
        )
        self._response_waiters[response_waiter.request_id] = response_waiter

        new_payload = {
            "request_id": response_waiter.request_id,
        }
        if payload is not None:
            new_payload.update(payload)

        await self._connector.send_message(
            topic=f"{self._topic_prefix}/{device_id}/{topic}",
            qos=qos,
            payload=self._payload_encoder(new_payload),
            ttl=ttl,
        )

        return response_waiter

    async def _result_callback(self, device_id: str, payload: dict[str, Any]) -> None:
        request_id = payload["request_id"]
        if request_id not in self._response_waiters:
            return

        if payload.get("code", 0) != 0:
            self._response_waiters[request_id]._set_exception(DeviceResponceError(payload["code"]))
            return

        self._response_waiters[request_id]._set_result(payload)

    async def reboot(
        self,
        device_id: str,
        payload: RebootPayload,
        ttl: int | None = 5,
    ) -> ResponseWaiter[AckResponse]:
        return await self._send_message(
            device_id=device_id,
            topic="client/reboot/set",
            qos=1,
            payload=payload,
            ttl=ttl,
        )

    async def set_state(
        self,
        device_id: str,
        payload: SetStatePayload,
        ttl: int | None = 5,
    ) -> ResponseWaiter[AckResponse]:
        return await self._send_message(
            device_id=device_id,
            topic="client/state/set",
            qos=2,
            payload=payload,
            ttl=ttl,
        )

    async def get_state(
        self,
        device_id: str,
        payload: GetStatePayload,
        ttl: int | None = 5,
    ) -> ResponseWaiter[GetStateResponse]:
        return await self._send_message(
            device_id=device_id,
            topic="client/state/get",
            qos=1,
            payload=payload,
            ttl=ttl,
        )
