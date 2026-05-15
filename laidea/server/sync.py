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

Capa 3: el workspace puede tener un `DiskStorage` inyectado (persistencia).

Capa 4: ownership. El handshake gana un tercer mensaje (`ownership`, después
de `welcome`). Si un cliente edita un archivo con dueño y no es el dueño, su
update NO se aplica: se vuelve una propuesta que se le manda al dueño, que la
aprueba (se aplica y converge todo el mundo) o la rechaza (al autor se le
revierte). Esto es la tesis del producto en código: prevenir con
coordinación, no fusionar después.
"""

from __future__ import annotations

import asyncio
import logging

from websockets.asyncio.server import ServerConnection, serve

from ..protocol import (
    ClaimMessage,
    InitMessage,
    LeaveMessage,
    OwnershipMessage,
    PresenceMessage,
    ProposalMessage,
    ResolveMessage,
    UpdateMessage,
    WelcomeMessage,
    decode,
    encode,
)
from ..state import DiskStorage, Ownership, Proposals, Roster, Workspace

logger = logging.getLogger(__name__)


class SyncServer:
    def __init__(self, storage: DiskStorage | None = None) -> None:
        # El workspace es el estado central. Todo lo demás (clientes, retransmisión)
        # gira alrededor de mantenerlo coherente entre todos los conectados.
        #
        # `storage` es inyectado (capa 3): el server real (__main__) pasa un
        # DiskStorage y el workspace se hidrata desde disco; los tests no pasan
        # nada y arrancan en memoria, vacíos y aislados entre sí — ese
        # aislamiento es un contrato que la suite necesita para no contaminarse.
        self.workspace = Workspace(storage=storage)
        self.workspace.cargar_de_disco()
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
        # Mapa inverso: client_id -> conexión. Capa 4 lo necesita para mandar
        # un mensaje dirigido a UN cliente concreto (al dueño de un archivo, al
        # autor de una propuesta), no un broadcast.
        self._conns: dict[str, ServerConnection] = {}
        # Capa 4: quién es dueño de qué (coordinación) y qué cambios tentativos
        # están esperando aprobación. Ambos efímeros, por sesión.
        self.ownership = Ownership()
        self.proposals = Proposals()

    async def _enviar_a(self, client_id: str, payload: str) -> None:
        """Manda `payload` a un único cliente por su identidad. Silencioso si no está.

        Capa 4 manda mensajes dirigidos (propuesta al dueño, reversión al
        autor). Si ese cliente no está conectado, simplemente no llega: el
        prototipo no tiene cola de reentrega (límite conocido, ver proposals.py).
        """
        conn = self._conns.get(client_id)
        if conn is None:
            return
        try:
            await conn.send(payload)
        except Exception:
            self.clients.discard(conn)

    async def _broadcast_todos(self, payload: str) -> None:
        """Manda `payload` a TODOS los clientes, incluido quien disparó la acción.

        A diferencia de `_broadcast` (que omite al emisor para no hacerle eco de
        su propio tecleo), aquí sí queremos llegar a todos: cuando el dueño
        aprueba una propuesta, el contenido es del *autor*, no del dueño, así
        que hasta el dueño que aprobó tiene que recibir y converger.
        """
        for client in list(self.clients):
            try:
                await client.send(payload)
            except Exception:
                self.clients.discard(client)

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
        self._conns[yo.client_id] = websocket
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
            # Tercer mensaje del handshake: el mapa de ownership actual. Mismo
            # criterio que welcome — va aparte, snapshot completo, idempotente.
            await websocket.send(
                encode(OwnershipMessage(owners=self.ownership.snapshot()))
            )

            async for raw in websocket:
                message = decode(raw)
                if isinstance(message, UpdateMessage):
                    dueño = self.ownership.owner(message.path)
                    if dueño is not None and dueño != yo.client_id:
                        # El archivo tiene dueño y NO eres tú: tu edición es
                        # tentativa. No se aplica ni se difunde — se guarda
                        # como propuesta y se le avisa al dueño. El autor
                        # conserva su texto local; nadie más ve el cambio
                        # todavía. "Editar primero, negociar después."
                        prop = self.proposals.put(
                            path=message.path,
                            author_id=yo.client_id,
                            author_name=yo.name,
                            content=message.content,
                        )
                        await self._enviar_a(
                            dueño, encode(ProposalMessage(proposal=prop))
                        )
                    else:
                        # Sin dueño, o eres tú el dueño: se aplica directo.
                        # Estado autoritativo PRIMERO, después se retransmite,
                        # para que un cliente que llegue en medio no vea un
                        # estado inconsistente.
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
                elif isinstance(message, ClaimMessage):
                    # Reclamar ser dueño de un path. Difundimos el mapa entero
                    # a todos (incluido quien reclamó: así su UI confirma si
                    # quedó como dueño o si ya lo tenía otro).
                    self.ownership.claim(message.path, yo.client_id)
                    await self._broadcast_todos(
                        encode(OwnershipMessage(owners=self.ownership.snapshot()))
                    )
                elif isinstance(message, ResolveMessage):
                    prop = self.proposals.get(message.proposal_id)
                    # Solo el dueño actual del archivo puede resolver. Si la
                    # propuesta ya no existe o quien resuelve no es el dueño,
                    # se ignora en silencio (carrera benigna: alguien más ya
                    # resolvió, o el ownership cambió).
                    if prop is not None and self.ownership.owner(
                        prop.path
                    ) == yo.client_id:
                        self.proposals.pop(message.proposal_id)
                        if message.accept:
                            # Aprobada: ahora sí se aplica y converge TODO el
                            # mundo (autor, dueño y demás) — por eso va a
                            # todos, no _broadcast (que omitiría al dueño que
                            # acaba de aprobar y necesita ver el contenido).
                            self.workspace.update(prop.path, prop.content)
                            await self._broadcast_todos(
                                encode(
                                    UpdateMessage(
                                        path=prop.path, content=prop.content
                                    )
                                )
                            )
                        else:
                            # Rechazada: al autor se le reenvía el contenido
                            # autoritativo para que su edición tentativa local
                            # se revierta a lo que de verdad hay.
                            await self._enviar_a(
                                prop.author_id,
                                encode(
                                    UpdateMessage(
                                        path=prop.path,
                                        content=self.workspace.snapshot().get(
                                            prop.path, ""
                                        ),
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
            self._conns.pop(yo.client_id, None)
            # Soltar el ownership de quien se va (ver ownership.py: sin esto el
            # archivo quedaría en deadlock, nadie podría aplicarle cambios). Si
            # cambió algo, todos necesitan el mapa nuevo.
            if self.ownership.release_all(yo.client_id):
                await self._broadcast(
                    websocket,
                    encode(OwnershipMessage(owners=self.ownership.snapshot())),
                )
            # Sus propuestas pendientes ya no tienen autor a quien converger.
            self.proposals.drop_author(yo.client_id)
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
