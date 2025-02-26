import asyncio
import logging
import re
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator, Callable, Coroutine

from .connectors.base import BaseConnector

log = logging.getLogger(__name__)


def _extract_device_id(topic_prefix: str, topic: str) -> str:
    m = re.search(rf"{topic_prefix}/(\w+)/", topic)
    if m is None:
        raise ValueError(f"Invalid topic: {topic}")

    return m.group(1)


class MessageHandler:
    def __init__(
        self,
        topic_prefix: str,
        topic: str,
        payload_decoder: Callable[[str | bytes], Any],
        callback_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._topic_prefix = topic_prefix
        self.topic = topic
        self._payload_decoder = payload_decoder
        self._callback_kwargs = callback_kwargs or {}
        self._callbacks: list[Callable[[str, dict[str, Any]], Coroutine]] = []

    def register_callback(self, callback: Callable[[str, dict[str, Any]], Coroutine]) -> None:
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[str, dict[str, Any]], Coroutine]) -> None:
        for i, f in enumerate(self._callbacks):
            if f is callback:
                del self._callbacks[i]
                return

        raise ValueError("Callback not found")

    async def _handle_message(self, topic: str, payload: str | bytes) -> None:
        decoded_payload = self._payload_decoder(payload)
        device_id = _extract_device_id(self._topic_prefix, topic)
        asyncio.gather(
            *[
                callback(device_id, decoded_payload, **self._callback_kwargs)
                for callback in self._callbacks
            ]
        )

    @asynccontextmanager
    async def handle_messages(self, connector: BaseConnector) -> AsyncIterator[None]:
        async with connector.subscribe(topic=self.topic, callback=self._handle_message):
            yield


class Dispatcher:
    def __init__(
        self,
        topic_prefix: str,
        payload_decoder: Callable[[str | bytes], Any],
        callback_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._payload_decoder = payload_decoder
        kwargs = {
            "payload_decoder": payload_decoder,
            "callback_kwargs": callback_kwargs,
        }

        self.begin = MessageHandler(f"{topic_prefix}/+/server/begin", **kwargs)
        self.reboot_ack = MessageHandler(f"{topic_prefix}/+/server/reboot/ack", **kwargs)
        self.config_ack = MessageHandler(f"{topic_prefix}/+/server/config/ack", **kwargs)
        self.config = MessageHandler(f"{topic_prefix}/+/server/config", **kwargs)
        self.setting_ack = MessageHandler(f"{topic_prefix}/+/server/setting/ack", **kwargs)
        self.setting = MessageHandler(f"{topic_prefix}/+/server/setting", **kwargs)
        self.state_ack = MessageHandler(f"{topic_prefix}/+/server/state/ack", **kwargs)
        self.state = MessageHandler(f"{topic_prefix}/+/server/state", **kwargs)
        self.state_info = MessageHandler(f"{topic_prefix}/+/server/state/info", **kwargs)

        self._callback_handlers = [
            self.begin,
            self.reboot_ack,
            self.config_ack,
            self.config,
            self.setting_ack,
            self.setting,
            self.state_ack,
            self.state,
            self.state_info,
        ]

    @asynccontextmanager
    async def start_handling(self, connector: BaseConnector) -> AsyncIterator[None]:
        async with AsyncExitStack() as exit_stack:
            for callback_handler in self._callback_handlers:
                await exit_stack.enter_async_context(callback_handler.handle_messages(connector))

            yield

    def register_callbacks(
        self, result_callback: Callable[[str, dict[str, Any]], Coroutine]
    ) -> None:
        self.reboot_ack.register_callback(result_callback)
        self.state_ack.register_callback(result_callback)
        self.config_ack.register_callback(result_callback)
        self.setting_ack.register_callback(result_callback)
        self.state.register_callback(result_callback)
