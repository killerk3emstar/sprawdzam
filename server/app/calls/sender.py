"""Serialised, never-raising sends on a WebSocket shared by several tasks."""

from __future__ import annotations

import asyncio
import contextlib

from starlette.websockets import WebSocket, WebSocketState


class SafeSender:
    """One lock per socket so concurrent tasks never interleave frames. After the socket is
    closed or a send fails, further sends are dropped and return False."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self._lock = asyncio.Lock()
        self.closed = False

    def _open(self) -> bool:
        return (
            not self.closed
            and self.ws.application_state == WebSocketState.CONNECTED
            and self.ws.client_state == WebSocketState.CONNECTED
        )

    async def send_json(self, data: object) -> bool:
        async with self._lock:
            if not self._open():
                return False
            try:
                await self.ws.send_json(data)
            except Exception:  # noqa: BLE001 - peer went away
                self.closed = True
                return False
            return True

    async def send_bytes(self, data: bytes) -> bool:
        async with self._lock:
            if not self._open():
                return False
            try:
                await self.ws.send_bytes(data)
            except Exception:  # noqa: BLE001 - peer went away
                self.closed = True
                return False
            return True

    async def close(self, code: int = 1000) -> None:
        async with self._lock:
            if self._open():
                with contextlib.suppress(Exception):
                    await self.ws.close(code)
            self.closed = True
