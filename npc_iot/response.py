import asyncio
import logging
import secrets
from typing import Any, Protocol

log = logging.getLogger(__name__)


async def _defult_request_id_generator() -> int:
    return secrets.randbits(16)


class RequestIdGenerator(Protocol):
    async def __call__(self) -> int: ...


class ResponseWaiter:
    def __init__(self, device_id: str, request_id: int, ttl: int | None) -> None:
        self.device_id = device_id
        self.request_id = request_id
        self.ttl = ttl
        self._future = asyncio.Future[dict[str, Any]]()

    def set_result(self, result: dict[str, Any]) -> None:
        self._future.set_result(result)

    def set_exception(self, exception: Exception) -> None:
        self._future.set_exception(exception)

    async def wait(self, timeout: float | None = 60) -> dict[str, Any]:
        if timeout is None:
            return await self._future
        return await asyncio.wait_for(self._future, timeout)
