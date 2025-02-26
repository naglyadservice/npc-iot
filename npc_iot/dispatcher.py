import asyncio
import logging
import re
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from typing import Any, AsyncIterator, Callable, Coroutine

from .connectors.base import BaseConnector

log = logging.getLogger(__name__)


def _extract_device_id(topic_prefix: str, topic: str) -> str:
    m = re.search(rf"{topic_prefix}/(\w+)/", topic)
    if m is None:
        raise ValueError(f"Invalid topic: {topic}")

    return m.group(1)


class MessageHandler:
    def __init__(self, topic: str, is_ack: bool = False, is_result: bool = False) -> None:
        self.topic = topic
        self.is_ack = is_ack
        self.is_result = is_result
        self._callbacks: list[Callable[[str, dict[str, Any]], Coroutine]] = []

    def register_callback(self, callback: Callable[[str, dict[str, Any]], Coroutine]) -> None:
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[str, dict[str, Any]], Coroutine]) -> None:
        for i, f in enumerate(self._callbacks):
            if f is callback:
                del self._callbacks[i]
                return

        raise ValueError("Callback not found")

    async def _handle_message(
        self,
        topic: str,
        payload: str | bytes,
        payload_decoder: Callable[[str | bytes], Any],
        topic_prefix: str,
        callback_kwargs: dict[str, Any],
    ) -> None:
        decoded_payload = payload_decoder(payload)
        device_id = _extract_device_id(topic_prefix, topic)
        asyncio.gather(
            *[
                callback(device_id, decoded_payload, **callback_kwargs)
                for callback in self._callbacks
            ]
        )

    @asynccontextmanager
    async def handle_messages(
        self,
        connector: BaseConnector,
        topic_prefix: str,
        payload_decoder: Callable[[str | bytes], Any],
        callback_kwargs: dict[str, Any] | None = None,
    ) -> AsyncIterator[None]:
        callback = partial(
            self._handle_message,
            payload_decoder=payload_decoder,
            topic_prefix=topic_prefix,
            callback_kwargs=callback_kwargs or {},
        )

        async with connector.subscribe(topic=f"{topic_prefix}{self.topic}", callback=callback):
            yield


class Dispatcher:
    begin = MessageHandler(topic="/+/server/begin")
    reboot_ack = MessageHandler(topic="/+/server/reboot/ack", is_ack=True)
    config_ack = MessageHandler(topic="/+/server/config/ack", is_ack=True)
    config = MessageHandler(topic="/+/server/config")
    setting_ack = MessageHandler(topic="/+/server/setting/ack", is_ack=True)
    setting = MessageHandler(topic="/+/server/server/setting")
    state_ack = MessageHandler(topic="/+/server/state/ack", is_ack=True)
    state = MessageHandler(topic="/+/server/state", is_result=True)
    state_info = MessageHandler(topic="/+/server/state/info")

    _callback_handlers = [
        begin,
        reboot_ack,
        config_ack,
        config,
        setting_ack,
        setting,
        state_ack,
        state,
        state_info,
    ]

    def __init__(
        self,
        topic_prefix: str,
        payload_decoder: Callable[[str | bytes], Any],
        callback_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._topic_prefix = topic_prefix
        self._payload_decoder = payload_decoder
        self._callback_kwargs = callback_kwargs

        self._handler_kwargs = {
            "topic_prefix": topic_prefix,
            "payload_decoder": payload_decoder,
            "callback_kwargs": callback_kwargs,
        }

    @asynccontextmanager
    async def start_handling(self, connector: BaseConnector) -> AsyncIterator[None]:
        async with AsyncExitStack() as exit_stack:
            for callback_handler in self._callback_handlers:
                await exit_stack.enter_async_context(
                    callback_handler.handle_messages(
                        connector,
                        topic_prefix=self._topic_prefix,
                        payload_decoder=self._payload_decoder,
                        callback_kwargs=self._callback_kwargs,
                    )
                )

            yield

    def register_callbacks(
        self, result_callback: Callable[[str, dict[str, Any]], Coroutine]
    ) -> None:
        for callback_handler in self._callback_handlers:
            if callback_handler.is_ack or callback_handler.is_result:
                callback_handler.register_callback(result_callback)
