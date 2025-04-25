import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from typing import AsyncIterator

from mqttproto import PropertyType, QoS
from mqttproto.async_client import AsyncMQTTClient

from .base import BaseConnector, CallbackType

logger = logging.getLogger(__name__)


class MqttprotoConnector(BaseConnector):
    def __init__(
        self,
        mqtt_client: AsyncMQTTClient,
        subscription_maximum_qos: int = 2,
    ) -> None:
        self._mqtt_client = mqtt_client
        self._subscription_maximum_qos = subscription_maximum_qos
        self._exit_stack = None

    async def _run_client(self, start_event: asyncio.Event, stop_event: asyncio.Event) -> None:
        async with self._mqtt_client:
            start_event.set()
            await stop_event.wait()

    async def __aenter__(self) -> None:
        # if context manager is not used in _mqtt_client, then use it
        if not hasattr(self._mqtt_client, "_exit_stack"):
            async with AsyncExitStack() as exit_stack:
                start_event = asyncio.Event()
                stop_event = asyncio.Event()

                task = asyncio.create_task(self._run_client(start_event, stop_event))

                exit_stack.push_async_callback(asyncio.gather, task)
                exit_stack.callback(stop_event.set)

                await start_event.wait()

                self._exit_stack = exit_stack.pop_all()

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(None, None, None)

    async def send_message(
        self,
        topic: str,
        qos: int,
        payload: bytes | str,
        ttl: int | None = None,
    ) -> None:
        properties = {}
        if ttl is not None:
            properties[PropertyType.MESSAGE_EXPIRY_INTERVAL] = ttl

        await self._mqtt_client.publish(topic, payload, qos=QoS(qos), properties=properties)

    async def _subscribe(self, topic: str, callback: CallbackType) -> None:
        async with self._mqtt_client.subscribe(
            topic,
            maximum_qos=QoS(self._subscription_maximum_qos),
        ) as subscription:
            with suppress(asyncio.CancelledError):
                async for message in subscription:
                    asyncio.create_task(callback(topic=message.topic, payload=message.payload))

    @asynccontextmanager
    async def subscribe(self, topic: str, callback: CallbackType) -> AsyncIterator[None]:
        logger.info(f"Subscribing to topic: {topic}")
        task = asyncio.create_task(self._subscribe(topic, callback))
        try:
            yield
        finally:
            task.cancel()
            await task
