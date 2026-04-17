import asyncio
import inspect
import logging
import re
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator, Callable, Coroutine, Generic, ParamSpec, TypeVar

from ..connectors.base import BaseConnector

log = logging.getLogger(__name__)


P = ParamSpec("P")

CallbackType = Callable[..., Coroutine]

ContextType = TypeVar("ContextType")


class MessageHandler(Generic[ContextType]):
    def __init__(
        self,
        topic_template: str,
        is_ack: bool = False,
        is_result: bool = False,
    ) -> None:
        self.topic_template = topic_template
        self.is_ack = is_ack
        self.is_result = is_result
        self._callbacks: list[CallbackType] = []
        self.mqtt_sub_topic = re.sub(r"\{[^}]+\}", "+", self.topic_template)
        self.path_vars = set(re.findall(r"\{([^}]+)\}", self.topic_template))
        self.provided_args = self.path_vars | {"payload", "ctx"}

    def register_callback(self, callback: CallbackType) -> None:
        sig = inspect.signature(callback)
        for param_name, param in sig.parameters.items():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                continue
            is_required = param.default is inspect.Parameter.empty

            if is_required and param_name not in self.provided_args:
                raise TypeError(
                    f"Failed to register callback '{callback.__name__}'.\n"
                    f"Signature mismatch: The callback expects a required positional argument '{param_name}', "
                    f"but it cannot be resolved from the current context.\n"
                    f"Available injectable arguments for topic template '{self.topic_template}' are: {sorted(list(self.provided_args))}.\n"
                    f"Hint: If '{param_name}' is intended to be optional, provide a default value (e.g., '{param_name}=None')."
                )

            if param_name in self.path_vars and param.annotation not in (
                inspect.Parameter.empty,
                str,
            ):
                raise TypeError(
                    f"Failed to register callback '{callback.__name__}'.\n"
                    f"Type mismatch: Path parameter '{param_name}' is extracted from the MQTT topic and must be of type 'str'.\n"
                    f"Found annotation: '{param.annotation.__name__ if hasattr(param.annotation, '__name__') else param.annotation}'.\n"
                    f"Hint: Change the type hint to '{param_name}: str'."
                )

        self._callbacks.append(callback)

    def remove_callback(self, callback: CallbackType) -> None:
        for i, f in enumerate(self._callbacks):
            if f is callback:
                del self._callbacks[i]
                return

        raise ValueError("Callback not found")

    async def _process_callbacks(
        self, path_params: dict[str, str], decoded_payload: Any, ctx: ContextType
    ) -> None:
        for callback in self._callbacks:
            sig = inspect.signature(callback)
            final_kwargs = {
                **path_params,
                "payload": decoded_payload,
                "ctx": ctx,
            }
            safe_kwargs = {
                k: v
                for k, v in final_kwargs.items()
                if k in sig.parameters
                or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            }
            asyncio.create_task(callback(**safe_kwargs))

    @asynccontextmanager
    async def handle_messages(
        self,
        connector: BaseConnector,
        topic_prefix: str,
        payload_decoder: Callable[[str | bytes], Any],
        ctx: ContextType,
        share_group_name: str | None = None,
    ) -> AsyncIterator[None]:
        safe_prefix = re.escape(topic_prefix)
        regex_pattern = re.sub(r"\{([^}]+)\}", r"(?P<\1>[^/]+)", self.topic_template)
        topic_regex = re.compile(f"^{safe_prefix}{regex_pattern}$")

        async def _wrapped_handle_message(topic: str, payload: str | bytes):
            try:
                decoded_payload = payload_decoder(payload)
            except Exception as e:
                log.error(f"Failed to decode payload, topic: {topic}", exc_info=e)
                return

            match = topic_regex.match(topic)
            if not match:
                log.error(f"Topic {topic} did not match regex {topic_regex.pattern}")
                return

            path_params = match.groupdict()

            asyncio.create_task(
                self._process_callbacks(
                    decoded_payload=decoded_payload,
                    path_params=path_params,
                    ctx=ctx,
                )
            )

        subscribe_topic = f"{topic_prefix}{self.mqtt_sub_topic}"
        if share_group_name and not (self.is_ack or self.is_result):
            subscribe_topic = f"$share/{share_group_name}/{subscribe_topic}"

        async with connector.subscribe(subscribe_topic, callback=_wrapped_handle_message):
            yield

    def __repr__(self) -> str:
        return f"<MessageHandler topic={self.topic_template} is_ack={self.is_ack} is_result={self.is_result}>"


class BaseDispatcher(Generic[ContextType]):
    def __init__(
        self,
        context: ContextType,
        share_group_name: str | None = None,
    ) -> None:
        self.context = context
        self._share_group_name = share_group_name

        for name, handler in self._get_callback_handlers():
            cloned = MessageHandler(
                topic_template=handler.topic_template,
                is_ack=handler.is_ack,
                is_result=handler.is_result,
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
                        ctx=self.context,
                        share_group_name=self._share_group_name,
                    )
                )

            yield

    def register_callbacks(self, result_callback: CallbackType) -> None:
        for _, callback_handler in self._get_callback_handlers():
            if callback_handler.is_ack or callback_handler.is_result:
                callback_handler.register_callback(result_callback)
