from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from fastapi import WebSocket


class NotificationsConnectionManager:
    """Track active notification websocket connections per authenticated user."""

    def __init__(self) -> None:
        self._connections: dict[int, list[WebSocket]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._send_lock: asyncio.Lock | None = None

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        """Accept a websocket and register it under the authenticated user."""

        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        self._connections[user_id].append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """Remove a websocket connection from the tracked user set."""

        user_connections = self._connections.get(user_id)
        if not user_connections:
            return

        self._connections[user_id] = [
            connection
            for connection in user_connections
            if connection is not websocket
        ]
        if not self._connections[user_id]:
            self._connections.pop(user_id, None)

    async def publish_to_user(
        self,
        user_id: int,
        payload: Mapping[str, Any],
    ) -> None:
        """Publish a realtime payload to every active connection of one user."""

        user_connections = list(self._connections.get(user_id, []))
        if not user_connections:
            return

        send_lock = self._send_lock
        if send_lock is None:
            send_lock = asyncio.Lock()
            self._send_lock = send_lock

        stale_connections: list[WebSocket] = []
        async with send_lock:
            for connection in user_connections:
                try:
                    await connection.send_json(dict(payload))
                except Exception:
                    stale_connections.append(connection)

        for connection in stale_connections:
            self.disconnect(user_id, connection)

    def publish_to_user_threadsafe(
        self,
        user_id: int,
        payload: Mapping[str, Any],
    ) -> None:
        """Schedule a realtime publish from synchronous service code."""

        loop = self._loop
        if loop is None or loop.is_closed():
            return

        loop.call_soon_threadsafe(
            asyncio.create_task,
            self.publish_to_user(user_id, payload),
        )


notifications_connection_manager = NotificationsConnectionManager()

__all__ = ["NotificationsConnectionManager", "notifications_connection_manager"]
