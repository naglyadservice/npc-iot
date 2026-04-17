import json
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest


class MockConnector:
    def __init__(self):
        self.sent_messages: list[dict[str, Any]] = []
        self._subscriptions: dict[str, Any] = {}
        self.send_message = AsyncMock(side_effect=self._record_send)

    async def _record_send(self, topic, qos, payload, ttl=None):
        self.sent_messages.append(
            {"topic": topic, "qos": qos, "payload": payload, "ttl": ttl}
        )

    async def __aenter__(self):
        return None

    async def __aexit__(self, *args):
        pass

    @asynccontextmanager
    async def subscribe(self, topic: str, callback):
        self._subscriptions[topic] = callback
        try:
            yield
        finally:
            self._subscriptions.pop(topic, None)

    async def inject_message(self, topic: str, payload: bytes | str):
        for sub_topic, callback in self._subscriptions.items():
            if self._topic_matches(sub_topic, topic):
                await callback(topic=topic, payload=payload)

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        pat_parts = pattern.split("/")
        top_parts = topic.split("/")
        if len(pat_parts) != len(top_parts):
            return False
        return all(p == "+" or p == t for p, t in zip(pat_parts, top_parts))


@pytest.fixture
def mock_connector():
    return MockConnector()
