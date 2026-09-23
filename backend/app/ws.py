import asyncio
import json
from datetime import datetime

from fastapi import WebSocket


def _default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


class Hub:
    """Broadcasts JSON events to connected clients, grouped by channel (admin, operator:<id>)."""

    def __init__(self):
        self.channels: dict[str, set[WebSocket]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, channel: str, ws: WebSocket):
        await ws.accept()
        self.channels.setdefault(channel, set()).add(ws)

    def disconnect(self, channel: str, ws: WebSocket):
        self.channels.get(channel, set()).discard(ws)

    async def _send(self, channel: str, payload: dict):
        dead = []
        for ws in list(self.channels.get(channel, set())):
            try:
                await ws.send_text(json.dumps(payload, default=_default))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(channel, ws)

    async def emit(self, event: str, data: dict, channels: list[str]):
        payload = {"event": event, "data": data, "ts": datetime.utcnow().isoformat()}
        for ch in channels:
            await self._send(ch, payload)

    def emit_sync(self, event: str, data: dict, channels: list[str]):
        """Schedule an emit from synchronous code running inside the event loop thread."""
        if self.loop is None:
            return
        asyncio.run_coroutine_threadsafe(self.emit(event, data, channels), self.loop)


hub = Hub()
