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
revierte). Crear un archivo hace dueño al creador. Esto es la tesis del
producto en código: prevenir con coordinación, no fusionar después.

Capa 5: prevención de colisiones por línea. Si el archivo NO tiene dueño,
antes de aplicar un update el servidor mira (vía presencia) si alguna línea
que el emisor pisa la está ocupando otro presente; si sí, rechaza el update
y le devuelve el contenido autoritativo. "Nunca dos en la misma línea." El
dueño tiene preferencia (sin lock). Sin CRDT: se previene, no se fusiona.

Capa 6: análisis semántico de impacto. Cada vez que un cambio a un `.py` se
aplica de verdad (edición directa o propuesta aprobada), el servidor calcula
qué símbolos top cambiaron y qué otros archivos los usan, y le manda un
`ImpactMessage` al dueño de cada archivo afectado. "Sin clickear, lo hace
solo." Solo cuando el código parsea: cero avisos por código a medio escribir.

Capa 7: identidad real. La app está CERRADA: al conectar no se manda nada
hasta que el cliente pasa por `_autenticar` (register/login/session). La
identidad ES el usuario (estable, persistido); el ownership ahora se indexa
por usuario y sobrevive a reiniciar. El token de sesión va firmado con HMAC.
"""

from __future__ import annotations

import asyncio
import logging
from secrets import token_hex

from websockets.asyncio.server import ServerConnection, serve

from ..analysis import impacto
from ..identity import (
    UserStore,
    crear_token,
    normalizar,
    usuario_de_token,
)
from ..protocol import (
    AuthErrorMessage,
    AuthOkMessage,
    ClaimMessage,
    ImpactMessage,
    InitMessage,
    LeaveMessage,
    LoginMessage,
    OwnershipMessage,
    PresenceMessage,
    ProposalMessage,
    RegisterMessage,
    ResolveMessage,
    SessionMessage,
    UpdateMessage,
    WelcomeMessage,
    decode,
    encode,
)
from ..state import (
    DiskStorage,
    Ownership,
    Proposals,
    Roster,
    Workspace,
    lineas_tocadas,
)

logger = logging.getLogger(__name__)


class SyncServer:
    def __init__(
        self,
        storage: DiskStorage | None = None,
        users: UserStore | None = None,
        ownership: Ownership | None = None,
        secret: str | None = None,
    ) -> None:
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
        # Capa 4/7: ownership ahora por usuario y persistido (inyectado).
        # Sin argumento = en memoria (tests). Las propuestas siguen efímeras.
        self.ownership = ownership if ownership is not None else Ownership()
        self.proposals = Proposals()
        # Capa 7: identidad real. `users` inyectado (en memoria si None, como
        # el resto del stack en tests). `secret` firma los tokens de sesión;
        # efímero por instancia si no se pasa (tests se loguean dentro de la
        # misma instancia, no dependen de cross-restart).
        self.users = users if users is not None else UserStore()
        self._secret = secret if secret is not None else token_hex(32)

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

    async def _notificar_impacto(
        self,
        path: str,
        viejo: str,
        nuevo: str,
        autor_id: str,
        autor_nombre: str,
    ) -> None:
        """Capa 6: avisa al dueño de cada archivo afectado por este cambio.

        "Sin clickear un botón, lo hace solo" (README). Calcula el impacto con
        el análisis puro y, agrupado por archivo afectado, le manda un
        `ImpactMessage` al dueño de ese archivo. Reglas mínimas:

        - Si el archivo afectado no tiene dueño, no hay a quién avisar.
        - Si el dueño del archivo afectado es el propio autor del cambio, no
          se le avisa: él lo hizo, ya lo sabe (evita auto-ruido).
        - Si el código no parsea, `impacto` devuelve {} y esto no manda nada:
          cero avisos por estados a medio escribir.
        """
        afectados = impacto(self.workspace.snapshot(), path, viejo, nuevo)
        if not afectados:
            return
        # Reagrupamos: símbolo->archivos  ==>  archivo_afectado->símbolos,
        # porque el aviso es "tu archivo X lo tocan estos símbolos".
        por_archivo: dict[str, list[str]] = {}
        for simbolo, archivos in afectados.items():
            for af in archivos:
                por_archivo.setdefault(af, []).append(simbolo)
        for af, simbolos in por_archivo.items():
            dueño = self.ownership.owner(af)
            if dueño is None or dueño == autor_id:
                continue
            await self._enviar_a(
                dueño,
                encode(
                    ImpactMessage(
                        source_path=path,
                        author_name=autor_nombre,
                        affected_path=af,
                        symbols=sorted(simbolos),
                    )
                ),
            )

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

    async def _autenticar(self, websocket: ServerConnection) -> str | None:
        """Compuerta de la capa 7: nada de app hasta autenticarse.

        Lee mensajes hasta que uno autentique (register/login/session) y
        devuelve el usuario normalizado. Mientras no lo logre responde
        `auth_error` y sigue escuchando en la MISMA conexión (el cliente
        reintenta sin reconectar). Devuelve None si la conexión se cierra sin
        autenticarse — la app jamás manda init/welcome a un desconocido.
        """
        async for raw in websocket:
            try:
                msg = decode(raw)
            except ValueError:
                await websocket.send(
                    encode(AuthErrorMessage(reason="mensaje inválido"))
                )
                continue
            if isinstance(msg, RegisterMessage):
                try:
                    return self.users.registrar(msg.username, msg.password)
                except ValueError as e:
                    await websocket.send(
                        encode(AuthErrorMessage(reason=str(e)))
                    )
            elif isinstance(msg, LoginMessage):
                if self.users.verificar(msg.username, msg.password):
                    return normalizar(msg.username)
                await websocket.send(
                    encode(
                        AuthErrorMessage(
                            reason="usuario o contraseña incorrectos"
                        )
                    )
                )
            elif isinstance(msg, SessionMessage):
                # Auto-login: token firmado por ESTE server y usuario que aún
                # existe. Reemplaza al token anónimo sin firmar de antes.
                user = usuario_de_token(msg.token, self._secret)
                if user is not None and self.users.existe(user):
                    return user
                await websocket.send(
                    encode(
                        AuthErrorMessage(reason="sesión inválida, inicia sesión")
                    )
                )
            else:
                await websocket.send(
                    encode(
                        AuthErrorMessage(reason="debes autenticarte primero")
                    )
                )
        return None

    async def handle(self, websocket: ServerConnection) -> None:
        """Handler por cada conexión. Capa 7: primero autenticar, luego app.

        Flujo: conectar -> _autenticar (cerrado: sin login no se entra) ->
        identidad = usuario real -> auth_ok + handshake (init/welcome/
        ownership) -> bucle de mensajes -> finally.

        Nota de prototipo: si el mismo usuario abre dos conexiones a la vez
        (dos pestañas/dispositivos), comparten identidad; la presencia y el
        canal dirigido se quedan con la última conexión. Aceptable para el
        público objetivo; el manejo fino multi-sesión es trabajo posterior.
        """
        self.clients.add(websocket)
        yo = None
        try:
            usuario = await self._autenticar(websocket)
            if usuario is None:
                return  # se desconectó sin autenticarse: nunca fue "alguien"
            yo = self.roster.asignar(usuario)
            self._ids[websocket] = yo.client_id
            self._conns[yo.client_id] = websocket
            logger.info(
                "usuario autenticado: %s (total: %d)",
                yo.client_id,
                len(self.clients),
            )
            # auth_ok con token de sesión fresco: el cliente lo guarda y lo
            # presenta como `session` al recargar (auto-login firmado).
            await websocket.send(
                encode(
                    AuthOkMessage(
                        username=yo.client_id,
                        token=crear_token(yo.client_id, self._secret),
                    )
                )
            )
            # Handshake normal (ya autenticado): workspace, presencia, ownership.
            await websocket.send(encode(InitMessage(files=self.workspace.snapshot())))
            await websocket.send(
                encode(
                    WelcomeMessage(
                        you=yo,
                        peers=self.roster.presentes(excepto=yo.client_id),
                    )
                )
            )
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
                        #
                        # Capa 5 — prevención de colisiones. Si el archivo NO
                        # tiene dueño, aplica el lock por línea: no puedes pisar
                        # una línea que otro presente está tocando. Si eres el
                        # dueño, tienes preferencia y el lock no te aplica
                        # ("el owner tiene preferencia", README).
                        # Contenido previo del archivo: lo necesitan tanto el
                        # lock de capa 5 como el análisis de impacto de capa 6,
                        # y hay que leerlo ANTES de aplicar. Una sola lectura.
                        viejo = self.workspace.snapshot().get(message.path, "")
                        if dueño is None:
                            tocadas = lineas_tocadas(viejo, message.content)
                            ocupadas = self.roster.lineas_ocupadas(
                                message.path, excepto=yo.client_id
                            )
                            if tocadas & ocupadas:
                                # Otro presente ya está en una de esas líneas:
                                # "el que la tocó primero escribe". Rechazamos
                                # el update ENTERO (sin CRDT no hay merge por
                                # línea robusto; en la práctica los updates son
                                # por pulsación, así que el alcance es mínimo) y
                                # le devolvemos al emisor el contenido
                                # autoritativo para que su edición se revierta.
                                await websocket.send(
                                    encode(
                                        UpdateMessage(
                                            path=message.path, content=viejo
                                        )
                                    )
                                )
                                continue
                        # ¿Es la PRIMERA vez que se ve este path? Entonces este
                        # update lo está *creando*. "El que la tocó primero
                        # escribe" + ownership invisible: quien crea un archivo
                        # es su dueño, sin botón. Antes un archivo nuevo nacía
                        # sin dueño y había que reclamarlo a mano (el bug).
                        es_nuevo = not self.workspace.exists(message.path)
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
                        if es_nuevo and dueño is None:
                            # Solo cuando el archivo nace SIN dueño (no cuando
                            # ya lo tenías reclamado y lo materializas con un
                            # update): si no, re-difundiríamos un mapa idéntico
                            # y meteríamos ruido en el stream.
                            self.ownership.claim(message.path, yo.client_id)
                            # Difundimos a todos (incluido el creador: su UI
                            # pinta "tuyo" sin que pida nada).
                            await self._broadcast_todos(
                                encode(
                                    OwnershipMessage(
                                        owners=self.ownership.snapshot()
                                    )
                                )
                            )
                        # Capa 6: ¿este cambio afecta código de alguien más?
                        await self._notificar_impacto(
                            message.path, viejo, message.content,
                            yo.client_id, yo.name,
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
                            viejo = self.workspace.snapshot().get(
                                prop.path, ""
                            )
                            self.workspace.update(prop.path, prop.content)
                            await self._broadcast_todos(
                                encode(
                                    UpdateMessage(
                                        path=prop.path, content=prop.content
                                    )
                                )
                            )
                            # Capa 6: el cambio aprobado (del autor) puede
                            # afectar archivos de otros dueños.
                            await self._notificar_impacto(
                                prop.path, viejo, prop.content,
                                prop.author_id, prop.author_name,
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
            if yo is not None:
                # Solo si llegó a autenticarse. Una conexión que se cerró en la
                # compuerta de login nunca fue "alguien": no hay nada que limpiar.
                self._ids.pop(websocket, None)
                # Soltamos el mapa conexión->id solo si sigue apuntando a ESTA
                # conexión: en una recarga la conexión nueva puede registrarse
                # antes de que corra este finally, y no queremos que el cierre
                # de la vieja borre el registro de la nueva (mismo usuario).
                if self._conns.get(yo.client_id) is websocket:
                    self._conns.pop(yo.client_id, None)
                # El ownership NO se toca al desconectar: ahora es por usuario y
                # persistido. El dueño lo sigue siendo aunque cierre la pestaña;
                # lo recupera al volver a entrar como el mismo usuario. Solo la
                # presencia es efímera.
                ultimo = self.roster.quitar(yo.client_id)
                # Avisamos del Leave solo si llegó a estar presente en algún
                # archivo (si nunca abrió nada, nadie lo tenía pintado).
                if ultimo is not None and ultimo.path is not None:
                    await self._broadcast(
                        websocket, encode(LeaveMessage(client_id=yo.client_id))
                    )
                logger.info(
                    "usuario desconectado: %s (total: %d)",
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
