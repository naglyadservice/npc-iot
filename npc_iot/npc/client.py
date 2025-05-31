import logging
from typing import Any, Callable, Generic, Type, TypeVar

from ..base.client import BaseClient
from ..response import ResponseWaiter
from .types import AckResponse, GetStatePayload, GetStateResponse, RebootPayload, SetStatePayload

try:
    import orjson as json  # type: ignore
except ImportError:
    import json

from ..connectors.base import BaseConnector
from ..response import RequestIdGenerator, _defult_request_id_generator
from .dispatcher import NpcDispatcher

log = logging.getLogger(__name__)

DispatcherType = TypeVar("DispatcherType", bound=NpcDispatcher)


class NpcClient(Generic[DispatcherType], BaseClient[DispatcherType]):
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
        topic_prefix: str = "v2",
        payload_encoder: Callable[[Any], str | bytes] = json.dumps,
        payload_decoder: Callable[[str | bytes], Any] = json.loads,
        request_id_generator: RequestIdGenerator = _defult_request_id_generator,
        dispatcher_class: Type[DispatcherType] = NpcDispatcher,
        dispatcher_kwargs: dict[str, Any] | None = None,
    ):
        super().__init__(
            connector=connector,
            host=host,
            port=port,
            ssl=ssl,
            client_id=client_id,
            username=username,
            password=password,
            clean_start=clean_start,
            topic_prefix=topic_prefix,
            payload_encoder=payload_encoder,
            payload_decoder=payload_decoder,
            request_id_generator=request_id_generator,
            dispatcher_class=dispatcher_class,
            dispatcher_kwargs=dispatcher_kwargs,
        )

    async def reboot(
        self,
        device_id: str,
        payload: RebootPayload,
        ttl: int | None = 5,
    ) -> ResponseWaiter[AckResponse]:
        return await self.send_message(
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
        return await self.send_message(
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
        return await self.send_message(
            device_id=device_id,
            topic="client/state/get",
            qos=1,
            payload=payload,
            ttl=ttl,
        )
