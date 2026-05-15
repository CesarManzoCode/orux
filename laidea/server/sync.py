"""Servidor de sincronización en tiempo real.

El servidor tiene tres responsabilidades, en este orden:

1. **Mantener el estado autoritativo del workspace.** Si dos clientes discrepan
   sobre qué dice un archivo, el servidor decide. La fuente de verdad vive aquí
   en memoria (más adelante, en disco).

2. **Llevar la cuenta de quién está conectado.** El set `clients` es el registro
   vivo de WebSockets activos. Cuando uno cae, sale del set.

3. **Retransmitir cambios.** Cuando un cliente manda un update, el servidor lo
   aplica al estado y lo manda a todos los demás clientes — pero no al emisor
   (eso causaría un eco molesto que rompería el cursor del que está escribiendo).

Capa 1: el servidor ya no maneja un Document, ahora maneja un Workspace
completo (múltiples archivos). El protocolo nuevo carga el `path` en cada
update así el servidor sabe a qué archivo aplicar el cambio.
"""

from __future__ import annotations

import asyncio
import logging

from websockets.asyncio.server import ServerConnection, serve

from ..protocol import InitMessage, UpdateMessage, decode, encode
from ..state import Workspace

logger = logging.getLogger(__name__)


class SyncServer:
    def __init__(self) -> None:
        # El workspace es el estado central. Todo lo demás (clientes, retransmisión)
        # gira alrededor de mantenerlo coherente entre todos los conectados.
        self.workspace = Workspace()
        # Set de conexiones activas. Lo usamos para difundir cambios a todos
        # menos al emisor original.
        self.clients: set[ServerConnection] = set()

    async def _broadcast(self, sender: ServerConnection, payload: str) -> None:
        """Manda `payload` a todos los clientes conectados excepto al emisor.

        Usamos `list(self.clients)` para evitar mutar el set mientras iteramos
        (si una conexión muere durante el envío, la sacamos del set en el catch).

        Si el envío a un cliente falla, asumimos que ese cliente ya no está
        sano y lo sacamos. No retransmitimos a clientes muertos — eso bloquearía
        el broadcast.
        """
        for client in list(self.clients):
            if client is sender:
                continue
            try:
                await client.send(payload)
            except Exception:
                self.clients.discard(client)

    async def handle(self, websocket: ServerConnection) -> None:
        """Handler por cada conexión nueva. Vive durante toda la sesión del cliente.

        El flujo es: registrar al cliente -> mandarle el snapshot inicial ->
        procesar mensajes hasta que se desconecte -> sacarlo del set.

        El `async for` itera mensajes a medida que llegan. Cuando el cliente
        cierra la conexión, el for termina solo y caemos al `finally`.
        """
        self.clients.add(websocket)
        logger.info("cliente conectado (total: %d)", len(self.clients))
        try:
            # Snapshot inicial: le mandamos al recién llegado todo lo que existe
            # ahora mismo en el workspace. Sin esto, vería pantalla vacía aunque
            # haya gente trabajando.
            await websocket.send(encode(InitMessage(files=self.workspace.snapshot())))

            async for raw in websocket:
                message = decode(raw)
                if isinstance(message, UpdateMessage):
                    # Aplicamos el cambio al estado autoritativo PRIMERO,
                    # después retransmitimos. Si retransmitiéramos antes de
                    # aplicar, un cliente nuevo que llegara entre esos dos
                    # momentos vería un estado inconsistente.
                    self.workspace.update(message.path, message.content)
                    await self._broadcast(
                        websocket,
                        encode(
                            UpdateMessage(
                                path=message.path,
                                content=message.content,
                            )
                        ),
                    )
                # Si llega un InitMessage del cliente lo ignoramos: init es
                # responsabilidad exclusiva del servidor. Cuando agreguemos más
                # tipos de mensaje (presencia, delete), van a aparecer más
                # ramas isinstance aquí.
        finally:
            self.clients.discard(websocket)
            logger.info("cliente desconectado (total: %d)", len(self.clients))

    async def run(self, host: str = "localhost", port: int = 8765) -> None:
        """Arranca el servidor WebSocket y lo deja escuchando para siempre.

        El `await asyncio.Future()` es un truco para bloquear el coroutine
        indefinidamente sin consumir CPU. Es lo que mantiene vivo el proceso
        hasta que lo mates con Ctrl+C.
        """
        async with serve(self.handle, host, port):
            logger.info("servidor escuchando en ws://%s:%d", host, port)
            await asyncio.Future()
