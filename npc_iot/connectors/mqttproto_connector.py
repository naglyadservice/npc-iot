import asyncio
import logging
import uuid
from contextlib import AsyncExitStack, asynccontextmanager, suppress
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
        health_check_min_interval: float = 1.0,
        health_check_max_interval: float = 30.0,
        health_check_backoff_factor: float = 1.5,
        health_check_timeout: float = 5.0,
        health_check_topic_prefix: str = "$client/healthcheck/",
        health_check_topic_suffix: str | None = None,
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

        self._health_check_min_interval = health_check_min_interval
        self._health_check_max_interval = health_check_max_interval
        self._health_check_backoff_factor = health_check_backoff_factor
        self._health_check_timeout = health_check_timeout
        if health_check_topic_suffix is None:
            health_check_topic_suffix = uuid.uuid4().hex

        self._health_probe_topic = (
            f"{health_check_topic_prefix.rstrip('/')}/{health_check_topic_suffix}"
        )
        self._health_probe_event = asyncio.Event()
        self._force_reconnect_event = asyncio.Event()
        self._background_tasks = set()

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
                await self._create_connection()

            except* (
                OSError,
                ConnectionRefusedError,
                ConnectionError,
                asyncio.TimeoutError,
                asyncio.CancelledError,
            ) as exc_group:
                # asyncio.CancelledError needs here Because library may raise it on disconnect
                if not self._stop_event.is_set():
                    exc = exc_group.exceptions[0]
                    logging.warning(
                        f"MQTT connection failed: {exc.__class__.__name__}: {exc}. Reconnecting in 1s..."
                    )
                    await asyncio.sleep(1)

            except* Exception as e:
                if not self._stop_event.is_set():
                    logger.exception(
                        f"Unexpected error in MQTT connection manager: {e.__class__.__name__}: {e}"
                    )
                    await asyncio.sleep(1)

    async def _create_connection(self):
        self._current_client = AsyncMQTTClient(**self._client_config)
        self._subscription_tasks = AsyncExitStack()
        self._force_reconnect_event.clear()

        try:
            await asyncio.wait_for(self._current_client.__aenter__(), timeout=5.0)

            logger.info("MQTT Connected!")
            await self._start_health_probe_subscription()
            if not await self._verify_subscriptions_work():
                logger.warning(
                    "MQTT subscriptions are not functional after connect, reconnecting..."
                )
                raise ConnectionError("Broker subscriptions not functional")

            self._connected_event.set()
            try:
                await self.resubscribe_all()
                health_task = asyncio.create_task(self._health_check_loop())

                try:
                    stop_task = asyncio.create_task(self._stop_event.wait())
                    reconnect_task = asyncio.create_task(self._force_reconnect_event.wait())
                    done, pending = await asyncio.wait(
                        [stop_task, reconnect_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()

                    if self._force_reconnect_event.is_set() and not self._stop_event.is_set():
                        raise ConnectionError("Health check failed, forcing reconnect")
                finally:
                    health_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await health_task

            finally:
                logger.info("MQTT Disconnected.")
                self._connected_event.clear()

        finally:
            with suppress(Exception):
                await self._current_client.__aexit__(None, None, None)

            self._current_client = None
            await self._subscription_tasks.aclose()
            self._subscription_tasks = None

    async def _start_health_probe_subscription(self):
        """Підписка на наш власний probe-топік."""

        async def probe_reader():
            try:
                async with self._current_client.subscribe(
                    self._health_probe_topic,
                    maximum_qos=QoS(1),
                ) as subscription:
                    async for _ in subscription:
                        self._health_probe_event.set()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"Health probe subscription error: {e}")

        await self._subscription_tasks.enter_async_context(_BackgroundTaskContext(probe_reader))

    async def _verify_subscriptions_work(self) -> bool:
        """Перевіряє, що broker роутить повідомлення. Якщо ні — з'єднання зламане."""
        # Даємо час підписці "прорости" на стороні брокера
        await asyncio.sleep(0.1)

        self._health_probe_event.clear()
        try:
            await self._current_client.publish(
                self._health_probe_topic,
                b"ping",
                qos=QoS(1),
            )
            await asyncio.wait_for(
                self._health_probe_event.wait(),
                timeout=self._health_check_timeout,
            )
            return True
        except asyncio.TimeoutError:
            return False
        except Exception as e:
            logger.warning(f"Health probe failed: {e}")
            return False

    async def _health_check_loop(self):
        interval = self._health_check_min_interval

        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(interval)

                if not await self._verify_subscriptions_work():
                    logger.warning("Health check failed, triggering reconnect")
                    self._force_reconnect_event.set()
                    return

                # Успіх — розтягуємо інтервал до максимуму
                interval = min(
                    interval * self._health_check_backoff_factor,
                    self._health_check_max_interval,
                )
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.exception(f"Health check loop error: {e}")

    async def resubscribe_all(self):
        subscriptions = list(self._active_subscriptions.items())
        for topic, callback in subscriptions:
            logger.info(f"Resubscribing to: {topic}")
            await self._start_subscription_reader(topic, callback)

    async def _start_subscription_reader(self, topic: str, callback: CallbackType):
        async def reader_task():
            try:
                async with self._current_client.subscribe(
                    topic, maximum_qos=QoS(self._subscription_maximum_qos)
                ) as subscription:
                    logger.info(f"Resubscribed to: {topic}")
                    async for message in subscription:
                        task = asyncio.create_task(
                            callback(topic=message.topic, payload=message.payload)
                        )
                        self._background_tasks.add(task)
                        task.add_done_callback(self._background_tasks.discard)

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
