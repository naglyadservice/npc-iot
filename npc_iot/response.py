import asyncio
import logging
from typing import Any, TypeVar

from .types import BaseResponse

log = logging.getLogger(__name__)


ResponseWaiterType = TypeVar("ResponseWaiterType", bound=BaseResponse)


class ResponseWaiter[ResponseWaiterType]:
    def __init__(self, device_id: str, request_id: int, ttl: int | None) -> None:
        self.device_id = device_id
        self.request_id = request_id
        self.ttl = ttl
        self._future = asyncio.Future()

    def _set_result(self, result: dict[str, Any]) -> None:
        if not self._future.done():
            self._future.set_result(result)
        else:
            log.warning(f"Future for {self.request_id} already done or cancelled")

    def _set_exception(self, exception: Exception) -> None:
        if not self._future.done():
            self._future.set_exception(exception)
        else:
            log.warning(f"Future for {self.request_id} already done or cancelled")

    async def wait(self, timeout: float | None = 60) -> ResponseWaiterType:
        if timeout is None:
            return await self._future
        return await asyncio.wait_for(self._future, timeout)
