import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from traceback import print_exc
from typing import AsyncIterator, Dict

from mqttproto import MQTTProtocolError, PropertyType, QoS
from mqttproto.async_client import AsyncMQTTClient

from .base import BaseConnector, CallbackType

logger = logging.getLogger(__name__)


class MqttprotoConnector(BaseConnector):
    def __init__(
        self,
        host: str,
        port: int,
        ssl: bool = False,
        client_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
        transport: str = "tcp",
        websocket_path: str | None = None,
        subscription_maximum_qos: int = 2,
        clean_start: bool | None = None,
    ) -> None:
        self._client_config = {
            "host_or_path": host,
            "port": port,
            "username": username,
            "password": password,
            "ssl": ssl,
            "client_id": client_id,
            "transport": transport,
            "websocket_path": websocket_path,
            "clean_start": clean_start,
            "stamina_kwargs": {
                "attempts": 1,
            },
        }

        self._subscription_maximum_qos = subscription_maximum_qos

        self._current_client: AsyncMQTTClient | None = None
        self._connected_event = asyncio.Event()
        self._manager_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

        self._active_subscriptions: Dict[str, CallbackType] = {}

        self._subscription_tasks: AsyncExitStack | None = None

    async def __aenter__(self) -> None:
        self._stop_event.clear()
        self._manager_task = asyncio.create_task(self._connection_manager_loop())

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        self._stop_event.set()
        if self._manager_task:
            self._manager_task.cancel()
            await self._manager_task

    async def _connection_manager_loop(self) -> None:
        logger.info("Connecting to MQTT broker...")
        while not self._stop_event.is_set():
            try:
                task = asyncio.create_task(self._create_connection())
                await task

            except* (
                OSError,
                ConnectionRefusedError,
                asyncio.TimeoutError,
                asyncio.CancelledError,
            ) as exc_group:
                # asyncio.CancelledError needs here becouse library may raise it on disconnect
                if not self._stop_event.is_set():
                    exc = exc_group.exceptions[0]
                    logging.warning(
                        f"MQTT connection failed: {exc.__class__.__name__}: {exc}. Reconnecting in 1s..."
                    )
                    await asyncio.sleep(1)
            except* Exception as e:
                logger.exception(
                    f"Unexpected error in MQTT connection manager: {e.__class__.__name__}: {e}"
                )
                print_exc()

    async def _create_connection(self):
        self._current_client = AsyncMQTTClient(**self._client_config)
        self._subscription_tasks = AsyncExitStack()

        try:
            await asyncio.wait_for(self._current_client.__aenter__(), timeout=5.0)

            logger.info("MQTT Connected!")
            self._connected_event.set()
            try:
                await self.resubscribe_all()
                await self._stop_event.wait()
            finally:
                logger.info("MQTT Disconnected.")
                self._connected_event.clear()

        finally:
            with suppress(Exception):
                await self._current_client.__aexit__(None, None, None)

            self._current_client = None
            await self._subscription_tasks.aclose()
            self._subscription_tasks = None

    async def resubscribe_all(self):
        for topic, callback in self._active_subscriptions.items():
            await self._start_subscription_reader(topic, callback)

    async def _start_subscription_reader(self, topic: str, callback: CallbackType):
        async def reader_task():
            try:
                async with self._current_client.subscribe(
                    topic, maximum_qos=QoS(self._subscription_maximum_qos)
                ) as subscription:
                    logger.info(f"Resubscribed to: {topic}")
                    async for message in subscription:
                        asyncio.create_task(callback(topic=message.topic, payload=message.payload))

            except asyncio.CancelledError:
                pass

            except Exception as e:
                if isinstance(e, MQTTProtocolError) and str(e).startswith(
                    "cannot perform this operation in the DISCONNECTED state"
                ):
                    return

                logger.warning(f"Subscription error for {topic}: {e.__class__.__name__}: {e}")

        await self._subscription_tasks.enter_async_context(_BackgroundTaskContext(reader_task))

    async def send_message(
        self,
        topic: str,
        qos: int,
        payload: bytes | str,
        ttl: int | None = None,
    ) -> None:
        if not self._connected_event.is_set():
            raise RuntimeError("MQTT client is not connected")

        properties = {}
        if ttl is not None:
            properties[PropertyType.MESSAGE_EXPIRY_INTERVAL] = ttl

        await self._current_client.publish(topic, payload, qos=QoS(qos), properties=properties)

    @asynccontextmanager
    async def subscribe(self, topic: str, callback: CallbackType) -> AsyncIterator[None]:
        logger.info(f"Registering subscription: {topic}")

        self._active_subscriptions[topic] = callback

        if self._connected_event.is_set():
            await self._start_subscription_reader(topic, callback)

        try:
            yield
        finally:
            logger.info(f"Unregistering subscription: {topic}")
            self._active_subscriptions.pop(topic, None)


class _BackgroundTaskContext:
    def __init__(self, coro_func):
        self.coro_func = coro_func
        self.task = None

    async def __aenter__(self):
        self.task = asyncio.create_task(self.coro_func())
        return self.task

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
