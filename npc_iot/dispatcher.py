import asyncio
import logging
import re
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Concatenate,
    Coroutine,
    Dict,
    ParamSpec,
)

from .connectors.base import BaseConnector

log = logging.getLogger(__name__)


def _extract_device_id(topic_prefix: str, topic: str) -> str:
    m = re.search(rf"{topic_prefix}/(\w+)/", topic)
    if m is None:
        raise ValueError(f"Invalid topic: {topic}")

    return m.group(1)


P = ParamSpec("P")

CallbackType = Callable[Concatenate[str, Dict[str, Any], P], Coroutine]


class MessageHandler:
    def __init__(self, topic: str, is_ack: bool = False, is_result: bool = False) -> None:
        self.topic = topic
        self.is_ack = is_ack
        self.is_result = is_result
        self._callbacks: list[CallbackType] = []

    def register_callback(self, callback: CallbackType) -> None:
        self._callbacks.append(callback)

    def remove_callback(self, callback: CallbackType) -> None:
        for i, f in enumerate(self._callbacks):
            if f is callback:
                del self._callbacks[i]
                return

        raise ValueError("Callback not found")

    async def _process_callbacks(
        self, device_id: str, decoded_payload: Any, **callback_kwargs: dict[str, Any]
    ) -> None:
        await asyncio.gather(
            *[
                callback(device_id, decoded_payload, **callback_kwargs)
                for callback in self._callbacks
            ]
        )

    async def _handle_message(
        self,
        topic: str,
        payload: str | bytes,
        payload_decoder: Callable[[str | bytes], Any],
        topic_prefix: str,
        callback_kwargs: dict[str, Any],
    ) -> None:
        try:
            decoded_payload = payload_decoder(payload)
        except Exception as e:
            log.error(f"Failed to decode payload, topic: {topic}, payload: {payload}", exc_info=e)
            return

        device_id = _extract_device_id(topic_prefix, topic)
        asyncio.create_task(self._process_callbacks(device_id, decoded_payload, **callback_kwargs))

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

    def __repr__(self) -> str:
        return (
            f"<MessageHandler topic={self.topic} is_ack={self.is_ack} is_result={self.is_result}>"
        )


class Dispatcher:
    def __init__(self, callback_kwargs: dict[str, Any] | None = None) -> None:
        self._callback_kwargs = callback_kwargs or {}

        self.begin = MessageHandler(topic="/+/server/begin")
        self.reboot_ack = MessageHandler(topic="/+/server/reboot/ack", is_ack=True)
        self.config_ack = MessageHandler(topic="/+/server/config/ack", is_ack=True)
        self.config = MessageHandler(topic="/+/server/config")
        self.setting_ack = MessageHandler(topic="/+/server/setting/ack", is_ack=True)
        self.setting = MessageHandler(topic="/+/server/server/setting")
        self.state_ack = MessageHandler(topic="/+/server/state/ack", is_ack=True)
        self.state = MessageHandler(topic="/+/server/state", is_result=True)
        self.state_info = MessageHandler(topic="/+/server/state/info")

    @property
    def _callback_handlers(self):
        return [value for value in self.__dict__.values() if isinstance(value, MessageHandler)]

    @asynccontextmanager
    async def start_handling(
        self,
        connector: BaseConnector,
        topic_prefix: str,
        payload_decoder: Callable[[str | bytes], Any],
    ) -> AsyncIterator[None]:
        async with AsyncExitStack() as exit_stack:
            for callback_handler in self._callback_handlers:
                await exit_stack.enter_async_context(
                    callback_handler.handle_messages(
                        connector,
                        topic_prefix=topic_prefix,
                        payload_decoder=payload_decoder,
                        callback_kwargs=self._callback_kwargs,
                    )
                )

            yield

    def register_callbacks(self, result_callback: CallbackType) -> None:
        for callback_handler in self._callback_handlers:
            if callback_handler.is_ack or callback_handler.is_result:
                callback_handler.register_callback(result_callback)
