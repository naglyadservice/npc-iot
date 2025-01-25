from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal, Protocol


class CallbackType(Protocol):
    async def __call__(self, topic: str, payload: bytes | str) -> None: ...


class BaseConnector(Protocol):
    async def __aenter__(self) -> None: ...

    async def __aexit__(self, exc_type, exc_value, traceback) -> None: ...

    async def send_message(
        self,
        topic: str,
        qos: Literal[0, 1, 2],
        payload: str | bytes,
        ttl: int | None = None,
    ) -> None: ...

    @asynccontextmanager
    async def subscribe(self, topic: str, callback: CallbackType) -> AsyncIterator[None]:
        yield
