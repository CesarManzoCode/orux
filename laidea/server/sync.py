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

Capa 2: el servidor también mantiene un `Roster` (quién está y dónde). Al
conectar le asigna al cliente una identidad anónima y le manda un Welcome con
su identidad + los demás presentes. Cuando un cliente manda su presencia
(archivo + línea), el servidor la fusiona con su identidad confiable y la
retransmite a los demás. Cuando un cliente cae, avisa con un Leave. La regla
de "no eco al emisor" es la misma que para los updates.
"""

from __future__ import annotations

import asyncio
import logging

from websockets.asyncio.server import ServerConnection, serve

from ..protocol import (
    InitMessage,
    LeaveMessage,
    PresenceMessage,
    UpdateMessage,
    WelcomeMessage,
    decode,
    encode,
)
from ..state import Roster, Workspace

logger = logging.getLogger(__name__)


class SyncServer:
    def __init__(self) -> None:
        # El workspace es el estado central. Todo lo demás (clientes, retransmisión)
        # gira alrededor de mantenerlo coherente entre todos los conectados.
        self.workspace = Workspace()
        # Set de conexiones activas. Lo usamos para difundir cambios a todos
        # menos al emisor original.
        self.clients: set[ServerConnection] = set()
        # Estado de presencia: quién está y dónde. Efímero, paralelo al
        # workspace (que es persistente). Ver state/presence.py.
        self.roster = Roster()
        # Puente entre las dos vistas de un mismo cliente: la conexión física
        # (ServerConnection) y su identidad lógica (client_id). Lo necesitamos
        # porque los updates llegan por la conexión pero la presencia se
        # razona por identidad.
        self._ids: dict[ServerConnection, str] = {}

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
        # El servidor asigna la identidad: el cliente no la elige (ver
        # state/presence.py). La guardamos atada a esta conexión.
        yo = self.roster.asignar()
        self._ids[websocket] = yo.client_id
        logger.info(
            "cliente conectado: %s (total: %d)", yo.client_id, len(self.clients)
        )
        try:
            # Snapshot inicial: le mandamos al recién llegado todo lo que existe
            # ahora mismo en el workspace. Sin esto, vería pantalla vacía aunque
            # haya gente trabajando.
            await websocket.send(encode(InitMessage(files=self.workspace.snapshot())))
            # Justo después, su identidad y quiénes más están presentes. Va como
            # mensaje aparte y no dentro del init a propósito: el snapshot del
            # workspace es un contrato estable, la presencia tiene otro ciclo.
            await websocket.send(
                encode(
                    WelcomeMessage(
                        you=yo,
                        peers=self.roster.presentes(excepto=yo.client_id),
                    )
                )
            )

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
                elif isinstance(message, PresenceMessage):
                    # El cliente solo nos dijo path+line. Fusionamos con la
                    # identidad confiable que el servidor ya tenía para esta
                    # conexión y difundimos el estado completo a los demás
                    # (sin eco al emisor: él ya sabe dónde está su propio cursor).
                    estado = self.roster.mover(
                        yo.client_id, message.path, message.line
                    )
                    if estado is not None:
                        await self._broadcast(
                            websocket,
                            encode(
                                PresenceMessage(
                                    client_id=estado.client_id,
                                    name=estado.name,
                                    color=estado.color,
                                    path=estado.path,
                                    line=estado.line,
                                )
                            ),
                        )
                # Si llega un InitMessage/WelcomeMessage/LeaveMessage del
                # cliente lo ignoramos: esos los origina solo el servidor.
        finally:
            self.clients.discard(websocket)
            self._ids.pop(websocket, None)
            ultimo = self.roster.quitar(yo.client_id)
            # Solo avisamos si la persona llegó a estar presente en algún
            # archivo. Si nunca abrió nada, nadie la tenía pintada y mandar un
            # Leave por ella sería ruido (y rompería tests que no usan presencia).
            if ultimo is not None and ultimo.path is not None:
                await self._broadcast(
                    websocket, encode(LeaveMessage(client_id=yo.client_id))
                )
            logger.info(
                "cliente desconectado: %s (total: %d)",
                yo.client_id,
                len(self.clients),
            )

    async def run(self, host: str = "localhost", port: int = 8765) -> None:
        """Arranca el servidor WebSocket y lo deja escuchando para siempre.

        El `await asyncio.Future()` es un truco para bloquear el coroutine
        indefinidamente sin consumir CPU. Es lo que mantiene vivo el proceso
        hasta que lo mates con Ctrl+C.
        """
        async with serve(self.handle, host, port):
            logger.info("servidor escuchando en ws://%s:%d", host, port)
            await asyncio.Future()
