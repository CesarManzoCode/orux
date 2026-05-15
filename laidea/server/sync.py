"""Servidor de sincronización en tiempo real (capa cero)."""

from __future__ import annotations

import asyncio
import logging

from websockets.asyncio.server import ServerConnection, serve

from ..protocol import InitMessage, UpdateMessage, decode, encode
from ..state import Document

logger = logging.getLogger(__name__)


class SyncServer:
    def __init__(self) -> None:
        self.document = Document()
        self.clients: set[ServerConnection] = set()

    async def _broadcast(self, sender: ServerConnection, payload: str) -> None:
        for client in list(self.clients):
            if client is sender:
                continue
            try:
                await client.send(payload)
            except Exception:
                self.clients.discard(client)

    async def handle(self, websocket: ServerConnection) -> None:
        self.clients.add(websocket)
        logger.info("cliente conectado (total: %d)", len(self.clients))
        try:
            await websocket.send(encode(InitMessage(content=self.document.content)))
            async for raw in websocket:
                message = decode(raw)
                if isinstance(message, UpdateMessage):
                    self.document.update(message.content)
                    await self._broadcast(
                        websocket,
                        encode(UpdateMessage(content=self.document.content)),
                    )
        finally:
            self.clients.discard(websocket)
            logger.info("cliente desconectado (total: %d)", len(self.clients))

    async def run(self, host: str = "localhost", port: int = 8765) -> None:
        async with serve(self.handle, host, port):
            logger.info("servidor escuchando en ws://%s:%d", host, port)
            await asyncio.Future()
