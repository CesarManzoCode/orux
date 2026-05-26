"""Servidor de sincronización en tiempo real — capa 15: multi-equipo.

Hasta capa 14 había UN workspace global: un solo equipo implícito. El
usuario pidió un sistema de verdad: varios equipos que no se enteran del
otro. Ahora cada equipo tiene su propio `TeamRuntime` (workspace,
presencia, ownership, propuestas, git, conexiones) y una conexión está
scopeada a UN equipo: un broadcast/propuesta/impacto jamás cruza de equipo.

Flujo de una conexión:

1. **Autenticar** (capa 7, sin cambios): register/login/session -> usuario.
2. **Lobby** (capa 15, nuevo): el usuario autenticado todavía NO ve nada.
   El server le manda sus equipos; él crea uno (queda admin), redime un
   código de invitación, o elige uno del que ya es miembro.
3. **Sesión de equipo**: recién acá el handshake normal (init/welcome/
   ownership/admin_info/git), scopeado al `TeamRuntime` de ESE equipo, y
   el bucle de mensajes (capas 4/5/6/9/10/12/13) operando sobre ese rt.

El "admin" de capas 12/13 ya no es global: es el rol 'admin' DENTRO del
equipo (su creador). El selector de owners del panel admin lista los
MIEMBROS del equipo, no todos los usuarios del sistema.

Las capas previas (4 ownership/tentativo, 5 colisiones por línea, 6
impacto, 8/9/10 git) NO cambiaron su lógica: sólo operan ahora sobre el
runtime del equipo en vez de sobre un estado global.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from secrets import token_hex

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from orux._rate import permitir_evento as _permitir_evento_rate
from orux.analysis.rename import Rename
from orux.identity import UserStore, crear_token
from orux.protocol import (
    AdminAssignManyMessage,
    AdminAssignMessage,
    AdminInfoMessage,
    AuthOkMessage,
    ClaimMessage,
    DeleteMessage,
    GitStatusMessage,
    InitMessage,
    LeaveMessage,
    OwnershipMessage,
    PresenceMessage,
    ProposalMessage,
    ResolveMessage,
    SaveMessage,
    TeamReadyMessage,
    UpdateMessage,
    WelcomeMessage,
    decode,
    encode,
)
from orux.ports import (
    GitPort,
    OwnershipStorePort,
    ProposalsStorePort,
    TeamStorePort,
    UserStorePort,
    WorkspaceStoragePort,
)
from orux.state import Ownership, Proposals, path_seguro
from orux.teams import MemTeamStore
from .config import (
    DEFAULT_WS_PORT,
    RATE_BURST,
    RATE_TASA,
    WS_MAX_QUEUE,
    WS_MAX_SIZE,
    WS_ORIGINS,
    _RateLimiter,
    _env_float,
    _env_int,
)
from . import auth_handshake, dispatch, eviction, seats
from . import impacto as impacto_mod
from . import lobby as lobby_mod
from .runtime import TeamRuntime
from .util import autor_git, ip_cliente, wrap_users

logger = logging.getLogger(__name__)

# Re-exportados desde `util.py` con su nombre histórico para callers internos.
# La función real vive en `util.py`; acá es solo alias.
_autor_git = autor_git
_ip_cliente = ip_cliente
_wrap_users = wrap_users


class SyncServer:
    def __init__(
        self,
        storage: WorkspaceStoragePort | None = None,
        users: UserStorePort | UserStore | None = None,
        ownership: Ownership | None = None,
        secret: str | None = None,
        git: GitPort | None = None,
        teams: TeamStorePort | None = None,
        runtime_factory=None,
        ownership_store: OwnershipStorePort | None = None,
        proposals_store: ProposalsStorePort | None = None,
    ) -> None:
        # Compat con la firma previa: si pasan storage/ownership/git
        # concretos (tests de git), ese trío se usa para el equipo que se
        # cree. Los tests tienen UN equipo, así que compartir es
        # indistinguible de "por equipo".
        self._base_storage = storage
        self._base_ownership = ownership
        self._base_git = git
        self._runtimes: dict[str, TeamRuntime] = {}
        # 3b: fábrica de runtime POR equipo (deploy: disco en
        # /data/ws/<team_id> + git ahí). None = comportamiento base de los
        # tests. `ownership_store` (PgOwnershipStore|None) persiste el mapa
        # de ownership por equipo: se CARGA al abrir el equipo y se GUARDA
        # tras cada cambio (el hot path sigue siendo el mapa en memoria).
        # `proposals_store` (PgProposalsStore|None) durabiliza las
        # propuestas tentativas: antes vivían SOLO en memoria del runtime
        # y un deploy a mitad de "Ana editó, Kai por aprobar" perdía el
        # estado. Mismo patrón que ownership_store: cargar al abrir el
        # equipo, escribir-a-través tras cada mutación; el hot path sigue
        # siendo el dict en memoria del runtime.
        self._runtime_factory = runtime_factory
        self._ownership_store = ownership_store
        self._proposals_store = proposals_store
        # Capa 7/15: usuarios SIEMPRE async para el server (envuelve el
        # sync de tests; PgUserStore pasa tal cual).
        self.users = _wrap_users(users)
        self._secret = secret if secret is not None else token_hex(32)
        # Robustez (seguridad M1): vida del token de sesión. Default 30 días
        # — cómodo para el dev (no re-loguea cada rato) y a la vez una fuga
        # tiene ventana acotada en vez de ser una llave eterna. `0` = sin
        # expiración (opt-out del operador; comportamiento legacy). Se
        # clampea para que un env tipo -1/9999999 no rompa (auditoría).
        self._token_ttl = _env_int(
            "ORUX_TOKEN_TTL_SEC", 30 * 24 * 3600, 0, 365 * 24 * 3600,
        )
        # Capa 15: equipos/membresía/invitaciones (async; None = memoria).
        self.teams = teams if teams is not None else MemTeamStore()
        # Lock por team_id para evitar carrera al construir el runtime
        # (BACKEND-AUDIT-0220): dos conexiones simultáneas al MISMO team
        # podrían invocar `runtime_factory` dos veces, levantar dos LSPs y
        # dos workspaces del MISMO disco. Granular: el lock de un equipo no
        # bloquea al de otro.
        self._rt_locks: dict[str, asyncio.Lock] = {}
        # Anti-abuso (capas nuevas): IP -> timestamps de registros / logins
        # recientes (ventana deslizante). Por-instancia a propósito: cada
        # server arranca con el contador limpio (tests).
        self._registro_buckets: dict[str, list[float]] = {}
        self._login_buckets: dict[str, list[float]] = {}
        # Capa 31 (cobro por asiento): clave secreta de Stripe — la MISMA
        # que el contenedor `api`. Con ella, cuando entra un miembro a un
        # equipo premium, el server sube la cantidad de asientos de su
        # suscripción. Vacía = billing sin configurar -> el ajuste se omite
        # (no rompe nada; un equipo sin suscripción tampoco se toca).
        self._stripe_secret = os.environ.get("STRIPE_SECRET_KEY", "").strip()
        # Tareas de fondo del ajuste de asientos: se guarda la referencia
        # para que el GC no las recoja a medias; se descartan al terminar.
        self._tareas_fondo: set[asyncio.Task] = set()
        # Lock por equipo para el ajuste de asientos: dos miembros que
        # entran casi a la vez no deben pisarse el conteo (cada tarea lee
        # los miembros y POSTea a Stripe; serializar garantiza que el POST
        # use el conteo fresco, no uno viejo).
        self._asientos_locks: dict[str, asyncio.Lock] = {}

    def _throttle(
        self, buckets: dict[str, list[float]], ip: str,
        tope: int, ventana: float,
    ) -> bool:
        """Ventana deslizante por IP: True = OK, False = la IP superó `tope`
        eventos en `ventana` segundos. El algoritmo (bucket + GC perezoso)
        vive en `orux/_rate.py` — antes había una copia byte-idéntica acá
        y otra en `adapters/inbound/http/app.py`."""
        return _permitir_evento_rate(buckets, ip, tope, ventana)

    def _throttle_registro(self, ip: str) -> bool:
        """Anti-abuso del registro: tope de registros por IP en ventana
        deslizante. El registro es PÚBLICO y el backoff por-conexión de
        `_autenticar` no lo frena — un bot que hace connect -> register ->
        disconnect arranca cada conexión con 0 fallos y un register exitoso
        retorna de inmediato. Tope generoso (default 20 cada 10 min): un
        equipo entero registrándose desde una misma oficina (NAT) no lo
        choca; un bot sí. Configurable con `ORUX_REGISTRO_MAX_POR_IP`."""
        return self._throttle(
            self._registro_buckets, ip,
            _env_int("ORUX_REGISTRO_MAX_POR_IP", 20, 1, 100_000), 600.0,
        )

    def _throttle_login(self, ip: str) -> bool:
        """Anti-fuerza-bruta del login: tope de intentos de login por IP en
        ventana deslizante. Mismo agujero que el registro — el backoff
        por-conexión se reinicia en cada reconexión, así que un bot prueba
        contraseñas reconectando. Tope más holgado que el registro (default
        40 cada 10 min): loguearse es más frecuente que registrarse, y el
        auto-login usa `session`, no `login`. Configurable con
        `ORUX_LOGIN_MAX_POR_IP`."""
        return self._throttle(
            self._login_buckets, ip,
            _env_int("ORUX_LOGIN_MAX_POR_IP", 40, 1, 100_000), 600.0,
        )

    # --- Capa 31: cobro por asiento -------------------------------------
    #
    # La lógica vive en `server/seats.py` (modularizado 2026-05-23). Acá
    # quedan los wrappers de instancia que cablean los atributos del server
    # (stripe_secret, teams, locks, tareas de fondo) al módulo puro.

    def _ajustar_asientos_bg(self, team_id: str) -> None:
        """Dispara el ajuste de asientos en SEGUNDO PLANO. Que un miembro
        entre a un equipo no debe esperar a una llamada de red a Stripe —
        el lobby sigue de largo. Sin `STRIPE_SECRET_KEY` no crea tarea
        (la guardia es acá para no instanciar la coroutine inútilmente)."""
        if not self._stripe_secret:
            return
        seats.disparar_ajuste(
            self._ajustar_asientos(team_id), self._tareas_fondo,
        )

    async def _ajustar_asientos(self, team_id: str) -> None:
        """Cara de instancia de `seats.ajustar_asientos`: cablea las
        dependencias del server."""
        await seats.ajustar_asientos(
            team_id=team_id,
            stripe_secret=self._stripe_secret,
            teams=self.teams,
            asientos_locks=self._asientos_locks,
        )

    async def _runtime_para(self, team_id: str) -> TeamRuntime:
        """Runtime del equipo, creado perezosamente. En deploy lo arma la
        `runtime_factory` (disco en /data/ws/<team_id> + git ahí); en tests
        (sin factory) usa el trío base/None -> cada equipo, estado propio en
        memoria = aislamiento. Si hay `ownership_store` (Postgres), el mapa
        del equipo se HIDRATA al abrirlo.

        BACKEND-AUDIT-0220: protegido por un lock por team_id para que dos
        handshakes simultáneos no construyan el mismo runtime dos veces."""
        rt = self._runtimes.get(team_id)
        if rt is not None:
            return rt
        lock = self._rt_locks.setdefault(team_id, asyncio.Lock())
        async with lock:
            # Re-check bajo el lock: otra corutina pudo haberlo creado.
            rt = self._runtimes.get(team_id)
            if rt is not None:
                return rt
            if self._runtime_factory is not None:
                rt = self._runtime_factory(team_id)
                if inspect.isawaitable(rt):
                    rt = await rt
            else:
                rt = TeamRuntime(
                    team_id=team_id,
                    storage=self._base_storage,
                    ownership=self._base_ownership,
                    git=self._base_git,
                )
            rt.team_id = team_id
            if self._ownership_store is not None:
                guardados = await self._ownership_store.cargar(team_id)
                for path, dueño in guardados.items():
                    rt.ownership.asignar(path, dueño)
            if self._proposals_store is not None:
                # Rehidrata las propuestas pendientes desde Postgres: si
                # el server reinició a mitad de "Ana editó, Kai por
                # aprobar", al abrir el equipo Kai vuelve a recibir la
                # propuesta en el handshake (vía `proposals.para`).
                rt.proposals.cargar(
                    await self._proposals_store.cargar(team_id)
                )
            self._runtimes[team_id] = rt
            return rt

    async def _persistir_own(self, rt: TeamRuntime) -> None:
        """Escribe-a-través el ownership del equipo a Postgres (si hay
        store). El mapa en memoria es la verdad; esto sólo lo durabiliza
        tras un cambio. Sin store (tests): no-op."""
        if self._ownership_store is not None:
            await self._ownership_store.guardar(
                rt.team_id, rt.ownership.snapshot()
            )

    async def _persistir_prop(self, rt: TeamRuntime, prop) -> None:
        """Escribe-a-través UNA propuesta tentativa. Mismo patrón que
        `_persistir_own`: el dict en memoria (rt.proposals) es la verdad
        del hot path; esto durabiliza el cambio. Sin store: no-op."""
        if self._proposals_store is not None:
            await self._proposals_store.guardar(rt.team_id, prop)

    async def _borrar_prop(
        self, rt: TeamRuntime, proposal_id: str
    ) -> None:
        """Quita la propuesta del store (Resolve aprobó/rechazó)."""
        if self._proposals_store is not None:
            await self._proposals_store.borrar(rt.team_id, proposal_id)

    async def _borrar_props_path(
        self, rt: TeamRuntime, path: str
    ) -> None:
        """Borra todas las propuestas sobre `path` del store (Delete del
        archivo deja la propuesta sin objeto)."""
        if self._proposals_store is not None:
            await self._proposals_store.borrar_path(rt.team_id, path)

    async def _borrar_props_todo(self, rt: TeamRuntime) -> None:
        """Limpia el set entero del equipo (clone destructivo: el
        workspace es otro repo, las propuestas viejas no aplican)."""
        if self._proposals_store is not None:
            await self._proposals_store.borrar_todo(rt.team_id)

    # --- Envío scopeado al equipo (rt) ---

    def _descartar(
        self, rt: TeamRuntime, client: ServerConnection, exc: Exception
    ) -> None:
        """Saca a un cliente cuyo envío falló. Antes esto tragaba TODA
        excepción sin rastro: un socket muerto (normal) era indistinguible
        de un bug de serialización que expulsaba clientes 'sin razón'. Una
        conexión cerrada es esperable (debug); cualquier otra cosa es un
        problema que debe dejar rastro (warning).

        Limpia también `_ids`/`_conns` del runtime (BACKEND-AUDIT-0240): si
        no, el mapping queda apuntando a un socket muerto y los siguientes
        envíos al client_id silenciosamente intentan escribir a un cadáver.

        Logs: el `client_id` se resuelve ANTES de borrar el mapping para
        poder dejarlo en el log (sin él, "se descartó alguien del equipo X"
        es ciego cuando un usuario reporta "no recibí mi propuesta"). Cae a
        "?" si la conexión nunca llegó a tener client_id asignado (envío
        durante el handshake antes de entrar al equipo).
        """
        cid = rt._ids.get(client, "?")
        rt.clients.discard(client)
        viejo_cid = rt._ids.pop(client, None)
        if viejo_cid is not None and rt._conns.get(viejo_cid) is client:
            rt._conns.pop(viejo_cid, None)
        if isinstance(exc, ConnectionClosed):
            logger.debug(
                "cliente %s caído en equipo %s (envío)", cid, rt.team_id,
            )
        else:
            logger.warning(
                "envío a %s falló en equipo %s, se descarta el cliente: %r",
                cid, rt.team_id, exc,
            )

    async def _enviar_a(self, rt: TeamRuntime, client_id: str, payload: str) -> None:
        """Manda `payload` a un único cliente del equipo. Silencioso si no está.

        Capa 4 manda mensajes dirigidos (propuesta al dueño, reversión al
        autor). Si ese cliente no está conectado, simplemente no llega: el
        prototipo no tiene cola de reentrega (límite conocido).
        """
        conn = rt._conns.get(client_id)
        if conn is None:
            return
        try:
            await conn.send(payload)
        except Exception as e:
            self._descartar(rt, conn, e)

    async def _broadcast_todos(self, rt: TeamRuntime, payload: str) -> None:
        """A TODOS los del equipo, incluido quien disparó la acción.

        A diferencia de `_broadcast` (omite al emisor para no hacerle eco de
        su tecleo), cuando el dueño aprueba una propuesta el contenido es del
        *autor*: hasta el dueño que aprobó tiene que recibir y converger.
        """
        for client in list(rt.clients):
            try:
                await client.send(payload)
            except Exception as e:
                self._descartar(rt, client, e)

    async def _broadcast(
        self, rt: TeamRuntime, sender: ServerConnection, payload: str
    ) -> None:
        """A todos los del equipo menos al emisor (eco rompería su cursor).

        Si el envío falla, ese cliente ya no está sano y se saca: no
        retransmitimos a muertos (bloquearía el broadcast).
        """
        for client in list(rt.clients):
            if client is sender:
                continue
            try:
                await client.send(payload)
            except Exception as e:
                self._descartar(rt, client, e)

    async def _notificar_impacto(
        self,
        rt: TeamRuntime,
        path: str,
        viejo: str,
        nuevo: str,
        autor_id: str,
        autor_nombre: str,
        rename: Rename | None = None,
    ) -> None:
        """Cable a `impacto.notificar_impacto` (modularizado 2026-05-23).
        Acá vive solo el cableado de la instancia; la lógica está en
        `server/impacto.py`."""
        await impacto_mod.notificar_impacto(
            self, rt, path, viejo, nuevo, autor_id, autor_nombre,
            rename=rename,
        )

    async def _propagar_rename(
        self,
        rt: TeamRuntime,
        path: str,
        viejo: str,
        nuevo: str,
        ren: Rename,
        autor_id: str,
        autor_nombre: str,
    ) -> None:
        """Cable a `impacto.propagar_rename` (modularizado 2026-05-23).
        Acá vive solo el cableado de la instancia; la lógica está en
        `server/impacto.py`."""
        await impacto_mod.propagar_rename(
            self, rt, path, viejo, nuevo, ren, autor_id, autor_nombre,
        )

    async def _git_status_encoded(self, rt: TeamRuntime) -> str | None:
        """Estado git del equipo, serializado, o None si no hay git."""
        if rt.git is None:
            return None
        e = await asyncio.to_thread(rt.git.estado)
        return encode(
            GitStatusMessage(
                available=e.disponible,
                branch=e.rama,
                changes=e.cambios,
                commits=e.commits,
            )
        )

    async def _admin_info_encoded(
        self, team_id: str, usuario: str
    ) -> str:
        """Capa 12/15: `admin_info` del EQUIPO. `is_admin` = rol 'admin' en
        este equipo (lo decide el server). La lista para el selector son los
        MIEMBROS del equipo (no todos los usuarios del sistema: aislamiento
        también de identidades)."""
        rol = await self.teams.rol(team_id, usuario)
        miembros = await self.teams.miembros(team_id)
        return encode(
            AdminInfoMessage(
                is_admin=rol == "admin",
                users=[m["usuario"] for m in miembros],
            )
        )

    async def _reiniciar_para_todos(self, rt: TeamRuntime) -> None:
        """Tras un clone destructivo en ESTE equipo: su workspace es otro
        repo. Tira el estado compartido viejo del equipo y re-inicializa a
        sus clientes. La presencia (Roster) NO se toca."""
        rt.workspace.recargar()
        rt.ownership.reset()
        rt._analizado.clear()  # capa 19: el workspace es otro, re-basea
        rt.reciclar_lsp()  # capa 17: el índice de pyright quedó obsoleto
        await self._persistir_own(rt)  # el ownership viejo ya no aplica
        rt.proposals = Proposals()
        await self._borrar_props_todo(rt)  # set entero invalidado
        init = encode(InitMessage(files=rt.workspace.snapshot()))
        own = encode(OwnershipMessage(owners=rt.ownership.snapshot()))
        gs = await self._git_status_encoded(rt)
        for conn in list(rt._conns.values()):
            try:
                await conn.send(init)
                await conn.send(own)
                if gs is not None:
                    await conn.send(gs)
            except Exception as e:
                # Fallo a mitad del re-init tras clone destructivo: el
                # cliente queda con estado mezclado. Se descarta con rastro
                # (antes era mudo, justo en el peor momento para perderlo).
                self._descartar(rt, conn, e)

    async def _enviar_git_status(
        self, rt: TeamRuntime, websocket: ServerConnection
    ) -> None:
        payload = await self._git_status_encoded(rt)
        if payload is not None:
            await websocket.send(payload)

    async def _autenticar(
        self, websocket: ServerConnection
    ) -> str | None:
        """Cable a `auth_handshake.autenticar` (modularizado 2026-05-23).
        La compuerta de la capa 7 (register/login/session, backoff,
        anti-fuerza-bruta) vive en `server/auth_handshake.py`."""
        return await auth_handshake.autenticar(self, websocket)

    async def _lobby(
        self, websocket: ServerConnection, usuario: str,
    ) -> str | None:
        """Cable a `lobby.lobby` (modularizado 2026-05-23). La compuerta
        de equipo (crear/redimir/seleccionar) vive en `server/lobby.py`."""
        return await lobby_mod.lobby(self, websocket, usuario)

    async def handle(self, websocket: ServerConnection) -> None:
        """Una conexión: autenticar -> lobby (elegir equipo) -> sesión del
        equipo. Hasta no estar en un equipo, la conexión no pertenece a
        ningún `rt` (no recibe broadcasts de nadie)."""
        usuario = await self._autenticar(websocket)
        if usuario is None:
            return  # se desconectó sin autenticarse: nunca fue "alguien"
        # auth_ok con token de sesión fresco (auto-login firmado al recargar).
        # Incluye el `epoch` actual del usuario: si después se revoca la
        # sesión, este token deja de valer sin tirar las del resto.
        epoch = await self.users.epoch(usuario)
        await websocket.send(
            encode(
                AuthOkMessage(
                    username=usuario,
                    token=crear_token(
                        usuario, self._secret, self._token_ttl,
                        epoch=epoch,
                    ),
                )
            )
        )
        team_id = await self._lobby(websocket, usuario)
        if team_id is None:
            return  # se fue desde el lobby sin elegir equipo
        await self._sesion_equipo(websocket, usuario, team_id)

    async def _sesion_equipo(
        self, websocket: ServerConnection, usuario: str, team_id: str
    ) -> None:
        """Sesión dentro de UN equipo. Todo (handshake + bucle) opera sobre
        el runtime de ese equipo: otro equipo no existe para esta conexión.
        """
        rt = await self._runtime_para(team_id)
        rt.clients.add(websocket)
        # Alguien entró: el runtime ya no está ocioso, cancelar la marca.
        rt._vacio_desde = None
        yo = rt.roster.asignar(usuario)
        rt._ids[websocket] = yo.client_id
        rt._conns[yo.client_id] = websocket
        eq = await self.teams.equipo(team_id)
        rol = await self.teams.rol(team_id, usuario)
        logger.info(
            "usuario %s entró al equipo %s (%s) — %d en el equipo",
            yo.client_id, team_id, eq["nombre"] if eq else "?", len(rt.clients),
        )
        try:
            # Confirmamos el equipo: lo que sigue es de ESTE equipo.
            await websocket.send(
                encode(
                    TeamReadyMessage(
                        team_id=team_id,
                        nombre=eq["nombre"] if eq else team_id,
                        rol=rol or "member",
                    )
                )
            )
            await websocket.send(
                encode(InitMessage(files=rt.workspace.snapshot()))
            )
            await websocket.send(
                encode(
                    WelcomeMessage(
                        you=yo,
                        peers=rt.roster.presentes(excepto=yo.client_id),
                    )
                )
            )
            await websocket.send(
                encode(OwnershipMessage(owners=rt.ownership.snapshot()))
            )
            await websocket.send(
                await self._admin_info_encoded(team_id, yo.client_id)
            )
            await self._enviar_git_status(rt, websocket)
            # Capa 4 (reentrega): si alguien propuso cambios a archivos de
            # este usuario MIENTRAS NO ESTABA (o el dueño se desconectó sin
            # resolver), las propuestas siguen en `rt.proposals` pero el aviso
            # original se mandó al void (`_enviar_a` con conn=None retorna).
            # Al final del handshake re-emitimos las pendientes que hoy le
            # tocan a este usuario, así no se entera "demasiado tarde".
            # Filtra por dueño ACTUAL: si el admin reasignó el archivo, el
            # aviso le toca al nuevo dueño, no a quien era cuando se creó.
            for prop in rt.proposals.para(yo.client_id, rt.ownership.owner):
                await websocket.send(encode(ProposalMessage(proposal=prop)))

            limiter = _RateLimiter(RATE_TASA, RATE_BURST)
            async for raw in websocket:
                # Rate-limit por conexión (BACKEND-AUDIT-0272): un cliente
                # que satura no debe ahogar al equipo entero. Excedido =
                # mensaje descartado en silencio (el cliente sano nunca lo
                # alcanza; el atacante sí). Si quisiéramos avisarle, otro
                # mensaje de error solo agrega tráfico.
                if not limiter.permitir():
                    logger.warning(
                        "rate-limit: descarto frame de %s en equipo %s",
                        yo.client_id, team_id,
                    )
                    continue
                try:
                    message = decode(raw)
                except (ValueError, KeyError, TypeError) as e:
                    # Un frame malformado/incompleto NO debe tumbar la
                    # conexion (antes: excepcion -> finally -> LeaveMessage,
                    # el usuario "desaparecia" sin rastro). Se loguea y se
                    # ignora ese frame, igual que _autenticar/_lobby.
                    logger.warning(
                        "mensaje invalido de %s en equipo %s: %s",
                        yo.client_id, team_id, e,
                    )
                    continue
                try:
                    await self._despachar(
                        rt, websocket, yo, team_id, message
                    )
                except ConnectionClosed:
                    raise  # el cliente se fue: que el finally limpie
                except Exception:
                    # Aislar la conexion culpable: un bug procesando ESTE
                    # mensaje (analisis sobre codigo arbitrario del cliente,
                    # etc.) no expulsa al usuario ni se traga el error.
                    logger.exception(
                        "error procesando %s de %s en equipo %s",
                        type(message).__name__, yo.client_id, team_id,
                    )
                    continue
        finally:
            rt.clients.discard(websocket)
            rt._ids.pop(websocket, None)  # mapeo por-conexión: siempre seguro
            # `client_id == usuario` (identidad determinista): dos pestañas /
            # una recarga rápida = el MISMO client_id con dos conexiones, y
            # la nueva se registra antes de que corra el finally de la vieja.
            # Si esta conexión ya NO es la registrada, otra está viva con esa
            # identidad: NO le borres la presencia (capa 5 dejaría de proteger
            # las líneas de un usuario que sigue editando) ni difundas Leave.
            es_la_actual = rt._conns.get(yo.client_id) is websocket
            if es_la_actual:
                rt._conns.pop(yo.client_id, None)
                # Ownership NO se toca al desconectar (por usuario,
                # persistido). Sólo la presencia es efímera.
                ultimo = rt.roster.quitar(yo.client_id)
                if ultimo is not None and ultimo.path is not None:
                    await self._broadcast(
                        rt, websocket,
                        encode(LeaveMessage(client_id=yo.client_id)),
                    )
            logger.info(
                "usuario %s salió del equipo %s — %d en el equipo",
                yo.client_id, team_id, len(rt.clients),
            )
            # Si fue el último, marca el momento — el barrido de
            # `_barrer_runtimes_ociosos` evicta el runtime entero tras
            # TTL si sigue vacío. Liberar RAM en lugar de retener
            # workspace + ownership + presencia + propuestas para un
            # equipo que ya nadie está usando.
            if not rt.clients:
                rt._vacio_desde = time.monotonic()


    # Mensajes que mutan estado compartido del equipo (workspace/ownership/
    # proposals): se procesan bajo `rt._estado_lock` para que su tramo
    # read-modify-write no se intercale con otro. El resto (presencia, git
    # con su _git_lock, invitaciones) NO toma el lock: sigue ágil.
    _MUTAN_ESTADO = (
        UpdateMessage,
        SaveMessage,
        DeleteMessage,
        ClaimMessage,
        AdminAssignMessage,
        AdminAssignManyMessage,
        ResolveMessage,
    )

    # Mensajes con UN path de cliente que se valida en la frontera y, si es
    # inseguro, hace descartar el mensaje entero. AdminAssignMany NO está
    # acá: lleva una LISTA y se filtra path-a-path en `_aplicar` (un path
    # basura no debe anular un reparto masivo legítimo). Resolve tampoco:
    # usa el path de la propuesta, estado del server ya validado al crearse.
    _CON_PATH_CLIENTE = (
        UpdateMessage,
        SaveMessage,
        DeleteMessage,
        ClaimMessage,
        AdminAssignMessage,
        PresenceMessage,
    )

    async def _despachar(
        self,
        rt: TeamRuntime,
        websocket: ServerConnection,
        yo,
        team_id: str,
        message,
    ) -> None:
        """Router: valida el path de la frontera y decide si el mensaje va
        bajo el lock de estado del equipo. El trabajo real lo hace
        `_aplicar`. Separado para que la guarda y el lock estén en UN lugar,
        no esparcidos por cada rama.
        """
        # --- Guarda de path (robustez M1): un path peligroso (`../x`,
        # absoluto, vacío, con NUL) NO debe entrar al estado en memoria ni
        # difundirse como archivo fantasma, aunque el disco lo bloquee
        # después. Se valida al RECIBIR, no solo en la frontera de disco.
        # PresenceMessage.path puede ser None (conectado, sin archivo
        # abierto): None es válido; un str sí se valida.
        if isinstance(message, self._CON_PATH_CLIENTE):
            p = message.path
            permiso = p is None and isinstance(message, PresenceMessage)
            if not permiso and not path_seguro(p):
                logger.warning(
                    "path inseguro descartado de %s en equipo %s: %r (%s)",
                    yo.client_id, team_id, p, type(message).__name__,
                )
                return

        if isinstance(message, self._MUTAN_ESTADO):
            async with rt._estado_lock:
                await self._aplicar(rt, websocket, yo, team_id, message)
        else:
            await self._aplicar(rt, websocket, yo, team_id, message)

    async def _es_admin_o_logear(
        self, team_id: str, client_id: str, accion: str,
    ) -> bool:
        """Compuerta admin con audit log al rechazar. Antes, las acciones
        admin (assign de ownership, invite) se ignoraban silenciosas si
        las pedía un member — sin rastro en logs. Compliance + diagnóstico
        necesitan saber QUIÉN intentó QUÉ y cuándo, aunque no haya
        consecuencia. Devuelve True si pasa (es admin), False si no
        (loguea WARN y deja al caller seguir/return)."""
        rol = await self.teams.rol(team_id, client_id)
        if rol == "admin":
            return True
        logger.warning(
            "admin-rechazado: %s (rol=%s) intentó %r en equipo %s",
            client_id, rol or "no-miembro", accion, team_id,
        )
        return False

    async def _aplicar(
        self,
        rt: TeamRuntime,
        websocket: ServerConnection,
        yo,
        team_id: str,
        message,
    ) -> None:
        """Cable a `dispatch.dispatch` (modularizado 2026-05-23). El
        cuerpo entero del despachador (un handler por message type) vive
        en `server/dispatch.py`. Aislado para que una excepción en un
        handler la capture el llamador (`_sesion_equipo` -> `_despachar`)
        sin matar la conexión. Sigue corriendo bajo `rt._estado_lock`
        cuando muta estado (`_despachar` decide eso por mensaje)."""
        await dispatch.dispatch(self, rt, websocket, yo, team_id, message)

    # --- Barridos de RAM (LSP + runtimes) -------------------------------
    #
    # La lógica vive en `server/eviction.py` (modularizado 2026-05-23).
    # Acá quedan los wrappers que cablean los atributos del server al
    # módulo puro, manteniendo la API histórica para no romper callers
    # internos.

    async def _barrer_lsp_ociosas(self, ttl: float) -> None:
        await eviction.barrer_lsp_ociosas(self._runtimes, ttl)

    def _runtime_evictable(self, rt: TeamRuntime, ttl: float, ahora: float) -> bool:
        return eviction.runtime_evictable(
            rt, ttl, ahora,
            tiene_proposals_store=self._proposals_store is not None,
        )

    async def _evictar_runtime(self, team_id: str) -> bool:
        return await eviction.evictar_runtime(
            team_id,
            runtimes=self._runtimes,
            rt_locks=self._rt_locks,
            asientos_locks=self._asientos_locks,
        )

    async def _barrer_runtimes_ociosos(self, ttl: float) -> None:
        await eviction.barrer_runtimes_ociosos(
            ttl,
            runtimes=self._runtimes,
            rt_locks=self._rt_locks,
            asientos_locks=self._asientos_locks,
            tiene_proposals_store=self._proposals_store is not None,
        )

    async def run(
        self, host: str = "localhost", port: int = DEFAULT_WS_PORT,
    ) -> None:
        """Arranca el server WebSocket y lo deja escuchando para siempre.

        `max_size`/`max_queue` aplican el tope HARD del frame antes de
        despachar al handler (BACKEND-AUDIT-0033 / -0271): un cliente que
        intenta colocar 50MB en una sola tecla NO consume RAM esperando ser
        decodificado. El `decode` también valida (defensa en profundidad)
        pero esto evita que el frame siquiera llegue al worker.
        """
        # TTL GENEROSO a propósito (default 20 min): tan largo que evictar
        # implica casi seguro que el equipo se fue, no que está pensando.
        # Configurable por si el operador del VPS quiere ajustar RAM vs
        # latencia-de-reentrada. Pagar el reindex ocasional << retener
        # cientos de MB de equipos que ya no están.
        ttl = _env_float("ORUX_LSP_IDLE_SEC", 1200.0, 60.0, 24 * 3600.0)
        # TTL de runtime ocioso (default 1h): un equipo SIN nadie
        # conectado desde hace una hora se evicta entero. Más holgado que
        # el TTL de LSP porque tirar un runtime invalida más cosas
        # (presencia, baseline de análisis); reconstruirlo desde el store
        # (ownership + propuestas) es barato pero el primer mensaje
        # paga la rehidratación. Floor en 5 min para que tests/dev no
        # esperen demasiado.
        rt_ttl = _env_float(
            "ORUX_RUNTIME_IDLE_SEC", 3600.0, 300.0, 7 * 24 * 3600.0,
        )
        async with serve(
            self.handle, host, port,
            max_size=WS_MAX_SIZE, max_queue=WS_MAX_QUEUE,
            origins=WS_ORIGINS,
        ):
            if WS_ORIGINS is None:
                origenes_desc = "* (sin filtro)"
            else:
                origenes_desc = ", ".join(
                    o if o is not None else "(sin Origin)" for o in WS_ORIGINS
                )
            logger.info(
                "servidor escuchando en ws://%s:%d "
                "(max_size=%d max_queue=%d origenes=%s)",
                host, port, WS_MAX_SIZE, WS_MAX_QUEUE, origenes_desc,
            )
            # Mismo patrón que `_ajustar_asientos_bg` (linea 341): guardar la
            # referencia en `_tareas_fondo` evita que el GC tire la tarea con
            # el log "Task was destroyed but it is pending" si algo falla.
            tarea_lsp = asyncio.create_task(self._barrer_lsp_ociosas(ttl))
            self._tareas_fondo.add(tarea_lsp)
            tarea_lsp.add_done_callback(self._tareas_fondo.discard)
            tarea_rt = asyncio.create_task(self._barrer_runtimes_ociosos(rt_ttl))
            self._tareas_fondo.add(tarea_rt)
            tarea_rt.add_done_callback(self._tareas_fondo.discard)
            await asyncio.Future()
