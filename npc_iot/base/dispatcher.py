import asyncio
import inspect
import logging
import re
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from typing import Any, AsyncIterator, Callable, Concatenate, Coroutine, Dict, ParamSpec, Protocol

from ..connectors.base import BaseConnector

log = logging.getLogger(__name__)


P = ParamSpec("P")

CallbackType = Callable[Concatenate[str, Dict[str, Any], P], Coroutine]


class DeviceIdParser(Protocol):
    def __call__(self, topic_prefix: str, topic: str) -> str: ...


def _parse_device_id(topic_prefix: str, topic: str) -> str:
    m = re.search(rf"{topic_prefix}/(\w+)/", topic)
    if m is None:
        raise ValueError(f"Invalid topic: {topic}")

    return m.group(1)


class MessageHandler:
    def __init__(
        self,
        topic: str,
        is_ack: bool = False,
        is_result: bool = False,
        device_id_parser: DeviceIdParser = _parse_device_id,
    ) -> None:
        self.topic = topic
        self.is_ack = is_ack
        self.is_result = is_result
        self._callbacks: list[CallbackType] = []
        self._device_id_parser = device_id_parser

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

        device_id = self._device_id_parser(topic_prefix, topic)
        asyncio.create_task(self._process_callbacks(device_id, decoded_payload, **callback_kwargs))

    @asynccontextmanager
    async def handle_messages(
        self,
        connector: BaseConnector,
        topic_prefix: str,
        payload_decoder: Callable[[str | bytes], Any],
        callback_kwargs: dict[str, Any] | None = None,
        share_group_name: str | None = None,
    ) -> AsyncIterator[None]:
        callback = partial(
            self._handle_message,
            payload_decoder=payload_decoder,
            topic_prefix=topic_prefix,
            callback_kwargs=callback_kwargs or {},
        )
        topic = f"{topic_prefix}{self.topic}"

        if share_group_name and not (self.is_ack or self.is_result):
            topic = f"$share/{share_group_name}/{topic}"

        async with connector.subscribe(topic, callback=callback):
            yield

    def __repr__(self) -> str:
        return (
            f"<MessageHandler topic={self.topic} is_ack={self.is_ack} is_result={self.is_result}>"
        )


class BaseDispatcher:
    def __init__(
        self, callback_kwargs: dict[str, Any] | None = None, share_group_name: str | None = None
    ) -> None:
        self._callback_kwargs = callback_kwargs or {}
        self._share_group_name = share_group_name

        for name, handler in self._get_callback_handlers():
            cloned = MessageHandler(
                topic=handler.topic,
                is_ack=handler.is_ack,
                is_result=handler.is_result,
                device_id_parser=handler._device_id_parser,
            )
            setattr(self, name, cloned)

    def _get_callback_handlers(self) -> list[tuple[str, MessageHandler]]:
        handlers: list[tuple[str, MessageHandler]] = []

        for name, member in inspect.getmembers(self):
            if isinstance(member, MessageHandler):
                handlers.append((name, member))

        return handlers

    @asynccontextmanager
    async def start_handling(
        self,
        connector: BaseConnector,
        topic_prefix: str,
        payload_decoder: Callable[[str | bytes], Any],
    ) -> AsyncIterator[None]:
        async with AsyncExitStack() as exit_stack:
            for _, callback_handler in self._get_callback_handlers():
                await exit_stack.enter_async_context(
                    callback_handler.handle_messages(
                        connector,
                        topic_prefix=topic_prefix,
                        payload_decoder=payload_decoder,
                        callback_kwargs=self._callback_kwargs,
                        share_group_name=self._share_group_name,
                    )
                )

            yield

    def register_callbacks(self, result_callback: CallbackType) -> None:
        for _, callback_handler in self._get_callback_handlers():
            if callback_handler.is_ack or callback_handler.is_result:
                callback_handler.register_callback(result_callback)
