import logging
from contextlib import AsyncExitStack
from typing import Any, Callable, Generic, Literal, Mapping, Self, Sequence, Type, TypeVar

try:
    import orjson as json  # type: ignore
except ImportError:
    import json

try:
    from mqttproto.async_client import AsyncMQTTClient
except ImportError:
    AsyncMQTTClient = None

from ..connectors.base import BaseConnector
from ..connectors.mqttproto_connector import MqttprotoConnector
from ..exception import DeviceResponseError
from ..response import RequestIdGenerator, ResponseWaiter, _default_request_id_generator
from .dispatcher import BaseDispatcher

log = logging.getLogger(__name__)


DispatcherType = TypeVar("DispatcherType", bound=BaseDispatcher)

# N-GATE v2.0 reads `req_id` for the db-sync/rule family and `request_id` for the
# state family, and tolerates the unused extra key — so both are sent by default and
# every topic correlates natively. Fleets whose firmware rejects unknown payload keys
# (or predates `req_id`) narrow this to the single key they speak.
DEFAULT_CORRELATION_KEYS: tuple[str, ...] = ("req_id", "request_id")


class BaseClient(Generic[DispatcherType]):
    dispatcher: DispatcherType

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
        topic_prefix: str = "",
        payload_encoder: Callable[[Any], str | bytes] = json.dumps,
        payload_decoder: Callable[[str | bytes], Any] = json.loads,
        request_id_generator: RequestIdGenerator = _default_request_id_generator,
        correlation_keys: Sequence[str] = DEFAULT_CORRELATION_KEYS,
        dispatcher_class: Type[DispatcherType] = BaseDispatcher,
        dispatcher_kwargs: dict[str, Any] | None = None,
    ) -> None:
        if connector is not None and not all(
            x is None for x in (host, port, ssl, client_id, username, password, clean_start)
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
                host=host,
                port=port,
                ssl=ssl,
                client_id=client_id,
                username=username,
                password=password,
                clean_start=clean_start,
            )

        self._connector = connector
        self._topic_prefix = topic_prefix
        self._request_id_generator = request_id_generator
        self._correlation_keys = tuple(correlation_keys)
        self._response_waiters: dict[int, ResponseWaiter] = {}
        self._payload_encoder = payload_encoder
        self._payload_decoder = payload_decoder

        self.dispatcher = dispatcher_class(**(dispatcher_kwargs or {}))
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

    def _remove_response_waiter(self, request_id: int) -> None:
        self._response_waiters.pop(request_id, None)

    async def send_message(
        self,
        topic_template: str,
        path_params: dict[str, str],
        qos: Literal[0, 1, 2],
        payload: Mapping[str, Any] | str | bytes | None,
        ttl: int | None = None,
        request_id: int | None = None,
        correlation_keys: Sequence[str] | None = None,
    ) -> ResponseWaiter:
        if request_id is None:
            request_id = await self._request_id_generator()

        response_waiter = ResponseWaiter(
            device_id=path_params.get("device_id", "unknown"),
            request_id=request_id,
            ttl=ttl,
            cancel_callback=self._remove_response_waiter,
        )
        self._response_waiters[response_waiter.request_id] = response_waiter

        if isinstance(payload, Mapping):
            keys = self._correlation_keys if correlation_keys is None else correlation_keys
            payload = {
                **dict.fromkeys(keys, response_waiter.request_id),
                **payload,
            }

        formatted_topic = topic_template.format(**path_params)
        full_topic = f"{self._topic_prefix}{formatted_topic}"

        await self.send_raw_message(
            topic=full_topic,
            qos=qos,
            payload=self._payload_encoder(payload),
            ttl=ttl,
        )

        return response_waiter

    async def send_raw_message(
        self,
        topic: str,
        qos: Literal[0, 1, 2],
        payload: str | bytes,
        ttl: int | None = None,
    ) -> None:
        await self._connector.send_message(
            topic=topic,
            qos=qos,
            payload=payload,
            ttl=ttl,
        )

    async def send_message_no_wait(
        self,
        topic_template: str,
        path_params: dict[str, str],
        qos: Literal[0, 1, 2],
        payload: Mapping[str, Any] | str | bytes | None,
        ttl: int | None = None,
    ) -> None:
        """Publish without creating a ResponseWaiter — for fire-and-forget messages
        (notifications, or acks the device does not respond to). Unlike send_message it
        injects NO correlation id, so the caller's payload is sent verbatim."""
        formatted_topic = topic_template.format(**path_params)
        full_topic = f"{self._topic_prefix}{formatted_topic}"
        encoded = payload if isinstance(payload, (str, bytes)) else self._payload_encoder(payload)
        await self.send_raw_message(topic=full_topic, qos=qos, payload=encoded, ttl=ttl)

    async def _result_callback(self, payload: dict[str, Any]) -> None:
        # Accept either correlation key: db-sync/rule acks carry `req_id`, state acks `request_id`.
        request_id = payload.get("req_id", payload.get("request_id"))
        if request_id is None:
            return

        if request_id not in self._response_waiters:
            return

        waiter = self._response_waiters.pop(request_id)

        if payload.get("code", 0) != 0:
            waiter._set_exception(DeviceResponseError(payload["code"]))
            return

        waiter._set_result(payload)
