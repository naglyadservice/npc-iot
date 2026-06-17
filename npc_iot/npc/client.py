import logging
from typing import Any, Callable, Generic, Type, TypeVar

from ..base.client import BaseClient
from ..response import ResponseWaiter
from .types import (
    AckResponse,
    AddPhonesMultiPayload,
    DbDeltaPayload,
    DelPhonesPayload,
    GetStatePayload,
    GetStateResponse,
    HistoryAckPayload,
    RebootPayload,
    RuleConfigPayload,
    SetStatePayload,
)

try:
    import orjson as json  # type: ignore
except ImportError:
    import json

from ..connectors.base import BaseConnector
from ..response import RequestIdGenerator, _default_request_id_generator
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
        request_id_generator: RequestIdGenerator = _default_request_id_generator,
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
        request_id: int | None = None,
    ) -> ResponseWaiter[AckResponse]:
        return await self.send_message(
            topic_template="/{device_id}/client/reboot/set",
            path_params={"device_id": device_id},
            qos=1,
            payload=payload,
            ttl=ttl,
            request_id=request_id,
        )

    async def set_state(
        self,
        device_id: str,
        payload: SetStatePayload,
        ttl: int | None = 5,
        request_id: int | None = None,
    ) -> ResponseWaiter[AckResponse]:
        return await self.send_message(
            topic_template="/{device_id}/client/state/set",
            path_params={"device_id": device_id},
            qos=2,
            payload=payload,
            ttl=ttl,
            request_id=request_id,
        )

    async def get_state(
        self,
        device_id: str,
        payload: GetStatePayload,
        ttl: int | None = 5,
        request_id: int | None = None,
    ) -> ResponseWaiter[GetStateResponse]:
        return await self.send_message(
            topic_template="/{device_id}/client/state/get",
            path_params={"device_id": device_id},
            qos=1,
            payload=payload,
            ttl=ttl,
            request_id=request_id,
        )

    async def add_phones(
        self,
        device_id: str,
        payload: AddPhonesMultiPayload,
        ttl: int | None = 5,
        request_id: int | None = None,
    ) -> ResponseWaiter[AckResponse]:
        return await self.send_message(
            topic_template="/{device_id}/client/phone/add_multi",
            path_params={"device_id": device_id},
            qos=1,
            payload=payload,
            ttl=ttl,
            request_id=request_id,
        )

    async def del_phones(
        self,
        device_id: str,
        payload: DelPhonesPayload,
        ttl: int | None = 5,
        request_id: int | None = None,
    ) -> ResponseWaiter[AckResponse]:
        return await self.send_message(
            topic_template="/{device_id}/client/phone/del",
            path_params={"device_id": device_id},
            qos=1,
            payload=payload,
            ttl=ttl,
            request_id=request_id,
        )

    # --- N-GATE v2.0 DB sync / history / rule config ---

    async def db_delta(
        self,
        device_id: str,
        payload: DbDeltaPayload,
        ttl: int | None = 15,
        request_id: int | None = None,
    ) -> ResponseWaiter[AckResponse]:
        """Apply a batch of upsert/delete ops to the device DB (`client/db/delta`)."""
        return await self.send_message(
            topic_template="/{device_id}/client/db/delta",
            path_params={"device_id": device_id},
            qos=1,
            payload=payload,
            ttl=ttl,
            request_id=request_id,
        )

    async def db_reset(
        self,
        device_id: str,
        ttl: int | None = 15,
        request_id: int | None = None,
    ) -> ResponseWaiter[AckResponse]:
        """Wipe the device DB (`client/db/reset`) before a full re-push."""
        return await self.send_message(
            topic_template="/{device_id}/client/db/reset",
            path_params={"device_id": device_id},
            qos=1,
            payload={},
            ttl=ttl,
            request_id=request_id,
        )

    async def db_stats_get(self, device_id: str) -> None:
        """Ask the device to (re)publish `server/db/stats`. Fire-and-forget: the stats
        arrive on a server topic the caller subscribes to, not as a 1:1 response."""
        await self.send_message_no_wait(
            topic_template="/{device_id}/client/db/stats/get",
            path_params={"device_id": device_id},
            qos=1,
            payload={},
        )

    async def rule_set(
        self,
        device_id: str,
        payload: RuleConfigPayload,
        ttl: int | None = 15,
        request_id: int | None = None,
    ) -> ResponseWaiter[AckResponse]:
        """Replace the device RuleConfig (`client/rule/set`) — hardware/rules/schedules."""
        return await self.send_message(
            topic_template="/{device_id}/client/rule/set",
            path_params={"device_id": device_id},
            qos=1,
            payload=payload,
            ttl=ttl,
            request_id=request_id,
        )

    async def history_ack(self, device_id: str, payload: HistoryAckPayload) -> None:
        """Confirm access-history up to `acked` (`client/history/ack`). Fire-and-forget,
        and the `req_id` echoes the received batch — so it is sent verbatim, uninjected."""
        await self.send_message_no_wait(
            topic_template="/{device_id}/client/history/ack",
            path_params={"device_id": device_id},
            qos=1,
            payload=payload,
        )
