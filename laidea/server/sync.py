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
import threading
import time
from secrets import token_hex

from websockets.asyncio.server import ServerConnection, serve

from ..analysis import impacto, motivos as motivos_de
from ..analysis.lsp import arrancar_lsp
from ..analysis.tiers import lenguaje_de
from ..plans import limites
from ..git import GitRepo
from ..identity import (
    UserStore,
    crear_token,
    normalizar,
    usuario_de_token,
)
from ..protocol import (
    AdminAssignManyMessage,
    AdminAssignMessage,
    AdminInfoMessage,
    AuthErrorMessage,
    AuthOkMessage,
    ClaimMessage,
    CloneMessage,
    CommitMessage,
    CreateInviteMessage,
    CreateTeamMessage,
    DeleteMessage,
    SaveMessage,
    GitRefreshMessage,
    GitResultMessage,
    GitStatusMessage,
    ImpactMessage,
    InitMessage,
    InviteCreatedMessage,
    LeaveMessage,
    LobbyMessage,
    LoginMessage,
    OwnershipMessage,
    PresenceMessage,
    ProposalMessage,
    PushMessage,
    RedeemInviteMessage,
    RegisterMessage,
    ResolveMessage,
    SelectTeamMessage,
    SessionMessage,
    TeamReadyMessage,
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
from ..teams import MemTeamStore, TeamError

logger = logging.getLogger(__name__)


def _autor_git(usuario: str) -> tuple[str, str]:
    """Identidad de commit a partir del usuario autenticado (capa 7).

    Si el usuario parece un email lo usamos como email y el nombre es la
    parte antes de la @. Si no, nombre = usuario y email sintético
    `usuario@laidea.local` (git exige un email; no tenemos uno real y no lo
    inventamos bonito a propósito — es honesto que sea sintético).
    """
    if "@" in usuario:
        return usuario.split("@", 1)[0], usuario
    return usuario, f"{usuario}@laidea.local"


class _UsuariosAsync:
    """Envuelve un `UserStore` síncrono (en memoria/JSON, tests) en una
    superficie async, para que el server haga SIEMPRE `await self.users.X()`
    sin importar si detrás hay JSON (tests) o Postgres (deploy). Si ya es
    async (PgUserStore) el server lo usa tal cual, sin envolver."""

    def __init__(self, base) -> None:
        self._b = base

    async def existe(self, u: str) -> bool:
        return self._b.existe(u)

    async def registrar(self, u: str, p: str) -> str:
        return self._b.registrar(u, p)

    async def verificar(self, u: str, p: str) -> bool:
        return self._b.verificar(u, p)


def _wrap_users(users):
    base = users if users is not None else UserStore()
    # PgUserStore ya es async (existe es coroutine): usar tal cual.
    if inspect.iscoroutinefunction(getattr(base, "existe", None)):
        return base
    return _UsuariosAsync(base)


class TeamRuntime:
    """Todo el estado vivo de UN equipo: su workspace, presencia, ownership,
    propuestas, repo git y conexiones. Un equipo no ve al otro porque cada
    uno tiene su runtime y los broadcasts se hacen sobre `rt.clients`.
    """

    def __init__(
        self,
        team_id: str = "",
        storage: DiskStorage | None = None,
        ownership: Ownership | None = None,
        git: GitRepo | None = None,
    ) -> None:
        self.team_id = team_id
        self.workspace = Workspace(storage=storage)
        self.workspace.cargar_de_disco()
        # Capa 17: dir del workspace en disco = rootUri de pyright. Sin
        # storage (tests en memoria) no hay dir => nunca se arranca LSP, se
        # usa la jerarquía de capa 16 (sandbox sigue verde).
        self._ws_dir = str(storage.root) if storage is not None else None
        # Capa 18: una sesión LSP POR LENGUAJE ("py"->pyright,
        # "jsts"->tsserver). Lazy: se arranca al 1er análisis de ESE
        # lenguaje y se cachea (incl. None = "no hay, no reintentar").
        self._lsp: dict[str, object] = {}
        self._lsp_uso: dict[str, float] = {}  # lang -> last use (monotonic)
        self._lsp_lock = threading.Lock()
        # Capa 19: último contenido ANALIZADO por archivo (baseline del
        # checkpoint). El impacto ya no corre por tecla: el diff es
        # baseline->contenido-al-Ctrl+S. Efímero (perderlo solo re-basea;
        # no es dato). Se siembra con el contenido PREVIO a la 1ª edición
        # de cada path (archivo nuevo="" / existente=lo cargado).
        self._analizado: dict[str, str] = {}
        self.clients: set[ServerConnection] = set()
        self.roster = Roster()
        self._ids: dict[ServerConnection, str] = {}
        self._conns: dict[str, ServerConnection] = {}
        self.ownership = ownership if ownership is not None else Ownership()
        self.proposals = Proposals()
        self.git = git
        # Serializa commit/clone/push de ESTE equipo (subprocess+fs sobre su
        # workspace). Por-runtime: el git de un equipo no bloquea al de otro.
        self._git_lock = asyncio.Lock()

    def lsp_sesion(self, lang: str | None, cap_langs: float | None = None):
        """Sesión LSP de ESTE equipo para `lang`, tibia: se arranca UNA vez
        (lazy, en el 1er análisis de ese lenguaje) y se reusa. Llamar
        SIEMPRE desde un hilo worker (spawn+handshake es bloqueante). None
        si el lenguaje no tiene server / no hay dir => degrada a capa 16.
        Cachear None evita reintentar el spawn en cada tecla.

        Capa 22: `cap_langs` = tope de lenguajes LSP del plan del equipo. Si
        ya hay `cap_langs` lenguajes con sesión y este es NUEVO, NO se
        arranca (degrada a tree-sitter/coarse, no rompe). Es el lever de
        costo real: premium = sin tope. El cap lo precomputa el server en
        el loop (el plan vive en un store async); acá solo se aplica.
        """
        if lang is None or self._ws_dir is None:
            return None
        with self._lsp_lock:
            if lang not in self._lsp:
                if cap_langs is not None and len(self._lsp) >= cap_langs:
                    return None  # tope del plan: no se paga el LSP extra
                self._lsp[lang] = arrancar_lsp(lang, self._ws_dir)
            # Marca de último uso para el barrido de ociosas: el server vive
            # mientras el equipo lo use; si no, se evicta y libera RAM.
            self._lsp_uso[lang] = time.monotonic()
            return self._lsp[lang]

    def evictar_lsp_ociosas(self, ttl: float) -> list[str]:
        """Cierra las sesiones sin uso hace más de `ttl` segundos y las
        olvida (el próximo análisis las re-arranca, degradando a tree-sitter
        mientras reindexan — net de capa 17). Así la RAM escala con equipos
        ACTIVOS, no totales. `ttl` se elige GENEROSO: tan largo que es casi
        seguro que el equipo se fue, no que está pensando un rato. Devuelve
        los lenguajes evictados (para loguear)."""
        ahora = time.monotonic()
        evictadas: list[str] = []
        with self._lsp_lock:
            for lang in list(self._lsp):
                ses = self._lsp[lang]
                if ahora - self._lsp_uso.get(lang, ahora) < ttl:
                    continue
                if ses is not None:
                    try:
                        ses.cerrar()
                    except Exception:  # noqa: BLE001
                        pass
                del self._lsp[lang]
                self._lsp_uso.pop(lang, None)
                evictadas.append(lang)
        return evictadas

    def reciclar_lsp(self) -> None:
        """Mata TODAS las sesiones y fuerza re-arranque al próximo análisis.
        Para el reinicio de capa 15 (clone destructivo cambia TODO el
        workspace: el índice de cada server quedó obsoleto)."""
        with self._lsp_lock:
            for ses in self._lsp.values():
                if ses is not None:
                    try:
                        ses.cerrar()
                    except Exception:  # noqa: BLE001
                        pass
            self._lsp = {}
            self._lsp_uso = {}


class SyncServer:
    def __init__(
        self,
        storage: DiskStorage | None = None,
        users: UserStore | None = None,
        ownership: Ownership | None = None,
        secret: str | None = None,
        git: GitRepo | None = None,
        teams: object | None = None,
        runtime_factory=None,
        ownership_store: object | None = None,
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
        self._runtime_factory = runtime_factory
        self._ownership_store = ownership_store
        # Capa 7/15: usuarios SIEMPRE async para el server (envuelve el
        # sync de tests; PgUserStore pasa tal cual).
        self.users = _wrap_users(users)
        self._secret = secret if secret is not None else token_hex(32)
        # Capa 15: equipos/membresía/invitaciones (async; None = memoria).
        self.teams = teams if teams is not None else MemTeamStore()

    async def _runtime_para(self, team_id: str) -> TeamRuntime:
        """Runtime del equipo, creado perezosamente. En deploy lo arma la
        `runtime_factory` (disco en /data/ws/<team_id> + git ahí); en tests
        (sin factory) usa el trío base/None -> cada equipo, estado propio en
        memoria = aislamiento. Si hay `ownership_store` (Postgres), el mapa
        del equipo se HIDRATA al abrirlo."""
        rt = self._runtimes.get(team_id)
        if rt is None:
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

    # --- Envío scopeado al equipo (rt) ---

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
        except Exception:
            rt.clients.discard(conn)

    async def _broadcast_todos(self, rt: TeamRuntime, payload: str) -> None:
        """A TODOS los del equipo, incluido quien disparó la acción.

        A diferencia de `_broadcast` (omite al emisor para no hacerle eco de
        su tecleo), cuando el dueño aprueba una propuesta el contenido es del
        *autor*: hasta el dueño que aprobó tiene que recibir y converger.
        """
        for client in list(rt.clients):
            try:
                await client.send(payload)
            except Exception:
                rt.clients.discard(client)

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
            except Exception:
                rt.clients.discard(client)

    async def _notificar_impacto(
        self,
        rt: TeamRuntime,
        path: str,
        viejo: str,
        nuevo: str,
        autor_id: str,
        autor_nombre: str,
    ) -> None:
        """Capa 6: avisa al dueño de cada archivo afectado por este cambio.

        "Sin clickear, lo hace solo" (README). Reglas: si el afectado no
        tiene dueño no hay a quién avisar; si el dueño es el propio autor no
        se le avisa (evita auto-ruido); si no parsea, `impacto` da {} y no
        manda nada. Todo scopeado al workspace/ownership de ESTE equipo.
        """
        # Capa 16: el análisis corre casi por tecla y antes era SÍNCRONO en
        # el event loop — bloqueaba presencia/locks/broadcasts de TODO el
        # equipo. Ahora todo el trabajo (incl. el lazy-arranque de pyright,
        # que hace spawn+handshake bloqueante) va a UN hilo: ni el parser C
        # ni el subproceso LSP tocan el event loop. Capa 17: la sesión LSP
        # del equipo (tibia) hace el fan-out resolución-real; si no hay
        # (sandbox/sin pyright) o falla, `impacto`/`motivos` degradan solos
        # a capa 16. Seguro: `snapshot()` es copia, todo lo demás strings.
        snap = rt.workspace.snapshot()
        # Capa 22: el cap de lenguajes LSP del plan se lee acá (el store es
        # async, vive en el loop) y se pasa al hilo. Premium = sin tope.
        plan = await self.teams.plan(rt.team_id)
        cap_langs = limites(plan)["max_langs"]

        def _analizar() -> tuple[dict, dict]:
            ses = rt.lsp_sesion(lenguaje_de(path), cap_langs)
            af = impacto(snap, path, viejo, nuevo, ses)
            if not af:
                return {}, {}
            return af, motivos_de(path, viejo, nuevo, ses)

        afectados, razones = await asyncio.to_thread(_analizar)
        if not afectados:
            return
        # Reagrupamos símbolo->archivos ==> archivo_afectado->símbolos.
        por_archivo: dict[str, list[str]] = {}
        for simbolo, archivos in afectados.items():
            for af in archivos:
                por_archivo.setdefault(af, []).append(simbolo)
        for af, simbolos in por_archivo.items():
            dueño = rt.ownership.owner(af)
            if dueño is None or dueño == autor_id:
                continue
            syms = sorted(simbolos)
            await self._enviar_a(
                rt,
                dueño,
                encode(
                    ImpactMessage(
                        source_path=path,
                        author_name=autor_nombre,
                        affected_path=af,
                        symbols=syms,
                        motivos=[razones.get(s, "") for s in syms],
                    )
                ),
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
        init = encode(InitMessage(files=rt.workspace.snapshot()))
        own = encode(OwnershipMessage(owners=rt.ownership.snapshot()))
        gs = await self._git_status_encoded(rt)
        for conn in list(rt._conns.values()):
            try:
                await conn.send(init)
                await conn.send(own)
                if gs is not None:
                    await conn.send(gs)
            except Exception:
                rt.clients.discard(conn)

    async def _enviar_git_status(
        self, rt: TeamRuntime, websocket: ServerConnection
    ) -> None:
        payload = await self._git_status_encoded(rt)
        if payload is not None:
            await websocket.send(payload)

    async def _autenticar(self, websocket: ServerConnection) -> str | None:
        """Compuerta de la capa 7: nada de app hasta autenticarse.

        Lee mensajes hasta que uno autentique (register/login/session) y
        devuelve el usuario normalizado. Mientras no lo logre responde
        `auth_error` y sigue escuchando en la MISMA conexión. None si la
        conexión se cierra sin autenticarse.
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
                    return await self.users.registrar(msg.username, msg.password)
                except ValueError as e:
                    await websocket.send(
                        encode(AuthErrorMessage(reason=str(e)))
                    )
            elif isinstance(msg, LoginMessage):
                if await self.users.verificar(msg.username, msg.password):
                    return normalizar(msg.username)
                await websocket.send(
                    encode(
                        AuthErrorMessage(
                            reason="usuario o contraseña incorrectos"
                        )
                    )
                )
            elif isinstance(msg, SessionMessage):
                user = usuario_de_token(msg.token, self._secret)
                if user is not None and await self.users.existe(user):
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

    async def _lobby(
        self, websocket: ServerConnection, usuario: str
    ) -> str | None:
        """Compuerta de equipo (capa 15). Autenticado pero sin equipo: NO ve
        nada. Le mandamos sus equipos y esperamos que cree uno, redima un
        código, o elija uno suyo. Devuelve el team_id elegido, o None si la
        conexión se cierra sin elegir.
        """
        async def _mandar_lobby(error: str = "") -> None:
            equipos = await self.teams.equipos_de(usuario)
            await websocket.send(
                encode(LobbyMessage(teams=equipos, error=error))
            )

        await _mandar_lobby()
        async for raw in websocket:
            try:
                msg = decode(raw)
            except ValueError:
                await _mandar_lobby("mensaje inválido")
                continue
            if isinstance(msg, CreateTeamMessage):
                try:
                    eq = await self.teams.crear_equipo(msg.nombre, usuario)
                    return eq["id"]
                except TeamError as e:
                    await _mandar_lobby(str(e))
            elif isinstance(msg, RedeemInviteMessage):
                try:
                    eq = await self.teams.redimir(msg.code, usuario)
                except TeamError as e:
                    # Capa 22: tope de plan (equipo lleno). Mensaje de
                    # upgrade, NO "código inválido": el código sigue vivo.
                    await _mandar_lobby(str(e))
                    continue
                if eq is not None:
                    return eq["id"]
                await _mandar_lobby("código inválido o ya usado")
            elif isinstance(msg, SelectTeamMessage):
                if await self.teams.es_miembro(msg.team_id, usuario):
                    return msg.team_id
                await _mandar_lobby("no sos miembro de ese equipo")
            else:
                # Cualquier mensaje de app antes de tener equipo: recordale
                # que primero hay que elegir/crear uno (la app sigue cerrada).
                await _mandar_lobby()
        return None

    async def handle(self, websocket: ServerConnection) -> None:
        """Una conexión: autenticar -> lobby (elegir equipo) -> sesión del
        equipo. Hasta no estar en un equipo, la conexión no pertenece a
        ningún `rt` (no recibe broadcasts de nadie)."""
        usuario = await self._autenticar(websocket)
        if usuario is None:
            return  # se desconectó sin autenticarse: nunca fue "alguien"
        # auth_ok con token de sesión fresco (auto-login firmado al recargar).
        await websocket.send(
            encode(
                AuthOkMessage(
                    username=usuario,
                    token=crear_token(usuario, self._secret),
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

            async for raw in websocket:
                message = decode(raw)
                if isinstance(message, UpdateMessage):
                    dueño = rt.ownership.owner(message.path)
                    if dueño is not None and dueño != yo.client_id:
                        # Archivo con dueño y no sos vos: edición tentativa.
                        # No se aplica ni difunde — se guarda como propuesta
                        # y se le avisa al dueño. "Editar primero, negociar
                        # después."
                        prop = rt.proposals.put(
                            path=message.path,
                            author_id=yo.client_id,
                            author_name=yo.name,
                            content=message.content,
                        )
                        await self._enviar_a(
                            rt, dueño, encode(ProposalMessage(proposal=prop))
                        )
                    else:
                        # Sin dueño, o sos el dueño: se aplica directo.
                        # Capa 5 (colisiones por línea): si NO tiene dueño y
                        # pisás una línea ocupada por otro presente, se
                        # rechaza el update entero. El dueño tiene preferencia.
                        viejo = rt.workspace.snapshot().get(message.path, "")
                        if dueño is None:
                            tocadas = lineas_tocadas(viejo, message.content)
                            ocupadas = rt.roster.lineas_ocupadas(
                                message.path, excepto=yo.client_id
                            )
                            if tocadas & ocupadas:
                                await websocket.send(
                                    encode(
                                        UpdateMessage(
                                            path=message.path, content=viejo
                                        )
                                    )
                                )
                                continue
                        # Primera vez que se ve el path = lo está creando:
                        # quien crea un archivo es su dueño, sin botón.
                        es_nuevo = not rt.workspace.exists(message.path)
                        # Capa 19: el impacto NO corre por tecla. Acá solo
                        # se siembra el baseline del checkpoint la 1ª vez
                        # que se toca el path (contenido PREVIO a editar);
                        # el análisis espera al `save` (Ctrl+S). El
                        # contenido sí sigue viajando en vivo (abajo).
                        rt._analizado.setdefault(message.path, viejo)
                        rt.workspace.update(message.path, message.content)
                        await self._broadcast(
                            rt,
                            websocket,
                            encode(
                                UpdateMessage(
                                    path=message.path,
                                    content=message.content,
                                )
                            ),
                        )
                        if es_nuevo and dueño is None:
                            rt.ownership.claim(message.path, yo.client_id)
                            await self._persistir_own(rt)
                            await self._broadcast_todos(
                                rt,
                                encode(
                                    OwnershipMessage(
                                        owners=rt.ownership.snapshot()
                                    )
                                ),
                            )
                elif isinstance(message, SaveMessage):
                    # Capa 19: el checkpoint del dev (Ctrl+S). NO guarda
                    # nada (el contenido ya está sincronizado); es el
                    # disparo del análisis. Diff baseline->ahora; el autor
                    # del aviso es quien marca el checkpoint. El baseline
                    # avanza siempre (haya o no impacto): el próximo Ctrl+S
                    # mide desde acá. No se retransmite (es un disparador,
                    # no estado a converger).
                    actual = rt.workspace.snapshot().get(message.path)
                    if actual is not None:
                        base = rt._analizado.get(message.path, "")
                        rt._analizado[message.path] = actual
                        await self._notificar_impacto(
                            rt, message.path, base, actual,
                            yo.client_id, yo.name,
                        )
                elif isinstance(message, DeleteMessage):
                    # Sólo borra el dueño, o cualquiera si no tiene dueño.
                    dueño = rt.ownership.owner(message.path)
                    if dueño is None or dueño == yo.client_id:
                        if rt.workspace.delete(message.path):
                            rt.proposals.drop_path(message.path)
                            # Capa 19: si se recrea, re-basea desde cero.
                            rt._analizado.pop(message.path, None)
                            cambio_owner = rt.ownership.liberar(message.path)
                            if cambio_owner:
                                await self._persistir_own(rt)
                            await self._broadcast_todos(
                                rt, encode(DeleteMessage(path=message.path))
                            )
                            if cambio_owner:
                                await self._broadcast_todos(
                                    rt,
                                    encode(
                                        OwnershipMessage(
                                            owners=rt.ownership.snapshot()
                                        )
                                    ),
                                )
                elif isinstance(message, ClaimMessage):
                    rt.ownership.claim(message.path, yo.client_id)
                    await self._persistir_own(rt)
                    await self._broadcast_todos(
                        rt,
                        encode(OwnershipMessage(owners=rt.ownership.snapshot())),
                    )
                elif isinstance(message, AdminAssignMessage):
                    # Capa 12/15: el admin DEL EQUIPO reparte ownership. Sólo
                    # el admin del equipo; un no-admin se ignora en silencio.
                    # `username` vacío = revocar. El destino debe ser miembro
                    # del equipo (asignar a alguien de afuera no tiene sentido
                    # y rompería el aislamiento).
                    if await self.teams.rol(team_id, yo.client_id) == "admin":
                        aplicado = False
                        if message.username:
                            destino = normalizar(message.username)
                            if await self.teams.es_miembro(team_id, destino):
                                rt.ownership.asignar(message.path, destino)
                                aplicado = True
                        else:
                            aplicado = rt.ownership.liberar(message.path)
                        if aplicado:
                            await self._persistir_own(rt)
                            await self._broadcast_todos(
                                rt,
                                encode(
                                    OwnershipMessage(
                                        owners=rt.ownership.snapshot()
                                    )
                                ),
                            )
                elif isinstance(message, AdminAssignManyMessage):
                    # Capa 13/15: reparto masivo, un solo broadcast. Misma
                    # compuerta (admin del equipo) y reglas que admin_assign.
                    if await self.teams.rol(team_id, yo.client_id) == "admin":
                        destino = (
                            normalizar(message.username)
                            if message.username else ""
                        )
                        valido = (
                            not destino
                            or await self.teams.es_miembro(team_id, destino)
                        )
                        aplicado = False
                        if valido:
                            for p in message.paths:
                                if not isinstance(p, str) or not p:
                                    continue
                                if destino:
                                    rt.ownership.asignar(p, destino)
                                    aplicado = True
                                elif rt.ownership.liberar(p):
                                    aplicado = True
                        if aplicado:
                            await self._persistir_own(rt)
                            await self._broadcast_todos(
                                rt,
                                encode(
                                    OwnershipMessage(
                                        owners=rt.ownership.snapshot()
                                    )
                                ),
                            )
                elif isinstance(message, CreateInviteMessage):
                    # Capa 15: el admin del equipo genera un código para
                    # invitar. Sólo el admin; un no-admin se ignora (igual
                    # que toda acción no autorizada: no se delata).
                    if await self.teams.rol(team_id, yo.client_id) == "admin":
                        try:
                            code = await self.teams.crear_invitacion(
                                team_id, yo.client_id
                            )
                            await self._enviar_a(
                                rt, yo.client_id,
                                encode(InviteCreatedMessage(code=code)),
                            )
                        except TeamError:
                            pass  # carrera benigna (dejó de ser admin, etc.)
                elif isinstance(message, ResolveMessage):
                    prop = rt.proposals.get(message.proposal_id)
                    # Sólo el dueño actual resuelve. Si ya no existe o no sos
                    # el dueño, se ignora (carrera benigna).
                    if prop is not None and rt.ownership.owner(
                        prop.path
                    ) == yo.client_id:
                        rt.proposals.pop(message.proposal_id)
                        if message.accept:
                            viejo = rt.workspace.snapshot().get(prop.path, "")
                            rt.workspace.update(prop.path, prop.content)
                            await self._broadcast_todos(
                                rt,
                                encode(
                                    UpdateMessage(
                                        path=prop.path, content=prop.content
                                    )
                                ),
                            )
                            await self._notificar_impacto(
                                rt, prop.path, viejo, prop.content,
                                prop.author_id, prop.author_name,
                            )
                        else:
                            await self._enviar_a(
                                rt,
                                prop.author_id,
                                encode(
                                    UpdateMessage(
                                        path=prop.path,
                                        content=rt.workspace.snapshot().get(
                                            prop.path, ""
                                        ),
                                    )
                                ),
                            )
                elif isinstance(message, PresenceMessage):
                    estado = rt.roster.mover(
                        yo.client_id, message.path, message.line
                    )
                    if estado is not None:
                        await self._broadcast(
                            rt,
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
                elif isinstance(message, GitRefreshMessage):
                    await self._enviar_git_status(rt, websocket)
                elif isinstance(message, CommitMessage):
                    if rt.git is None:
                        await self._enviar_a(
                            rt, yo.client_id,
                            encode(GitResultMessage(False, "git no disponible")),
                        )
                    else:
                        msg = (message.message or "").strip()[:500]
                        if not msg:
                            await self._enviar_a(
                                rt, yo.client_id,
                                encode(GitResultMessage(
                                    False, "escribí un mensaje de commit")),
                            )
                        else:
                            nombre, email = _autor_git(yo.client_id)
                            async with rt._git_lock:
                                ok, detalle = await asyncio.to_thread(
                                    rt.git.commitear, msg, nombre, email
                                )
                            await self._enviar_a(
                                rt, yo.client_id,
                                encode(GitResultMessage(ok, detalle)),
                            )
                            if ok:
                                payload = await self._git_status_encoded(rt)
                                if payload is not None:
                                    await self._broadcast_todos(rt, payload)
                elif isinstance(message, CloneMessage):
                    if rt.git is None:
                        await self._enviar_a(
                            rt, yo.client_id,
                            encode(GitResultMessage(False, "git no disponible")),
                        )
                    else:
                        async with rt._git_lock:
                            ok, detalle = await asyncio.to_thread(
                                rt.git.clonar,
                                message.url, message.username, message.token,
                            )
                            if ok:
                                await self._reiniciar_para_todos(rt)
                        await self._enviar_a(
                            rt, yo.client_id,
                            encode(GitResultMessage(ok, detalle)),
                        )
                elif isinstance(message, PushMessage):
                    if rt.git is None:
                        await self._enviar_a(
                            rt, yo.client_id,
                            encode(GitResultMessage(False, "git no disponible")),
                        )
                    else:
                        # Capa 21b: la rama destino la ELIGE el usuario.
                        # Vacío = la rama de publicación del equipo (default
                        # seguro: force-with-lease + PR; laidea es su único
                        # escritor). Cualquier otra (p.ej. main) = push
                        # normal SIN forzar (capa 10: non-ff honesto, jamás
                        # pisa historia compartida). laidea decide force-o-no
                        # por el destino; el usuario solo elige a dónde.
                        rama_eq = f"laidea/{rt.team_id}"
                        destino = (message.rama or "").strip() or rama_eq
                        async with rt._git_lock:
                            if destino == rama_eq:
                                ok, detalle, pr_url = await asyncio.to_thread(
                                    rt.git.push_a_rama,
                                    message.username, message.token,
                                    rama_eq, message.url or None,
                                )
                            else:
                                ok, detalle = await asyncio.to_thread(
                                    rt.git.push,
                                    message.username, message.token,
                                    message.url or None, destino,
                                )
                                pr_url = ""
                        await self._enviar_a(
                            rt, yo.client_id,
                            encode(GitResultMessage(ok, detalle, pr_url)),
                        )
                        if ok:
                            payload = await self._git_status_encoded(rt)
                            if payload is not None:
                                await self._broadcast_todos(rt, payload)
                # Init/Welcome/Leave del cliente se ignoran: los origina el
                # server. Mensajes de lobby acá tampoco aplican (ya hay equipo).
        finally:
            rt.clients.discard(websocket)
            rt._ids.pop(websocket, None)
            # Soltamos conexión->id sólo si sigue apuntando a ESTA conexión:
            # en una recarga la nueva puede registrarse antes de este finally.
            if rt._conns.get(yo.client_id) is websocket:
                rt._conns.pop(yo.client_id, None)
            # Ownership NO se toca al desconectar (por usuario, persistido).
            # Sólo la presencia es efímera.
            ultimo = rt.roster.quitar(yo.client_id)
            if ultimo is not None and ultimo.path is not None:
                await self._broadcast(
                    rt, websocket, encode(LeaveMessage(client_id=yo.client_id))
                )
            logger.info(
                "usuario %s salió del equipo %s — %d en el equipo",
                yo.client_id, team_id, len(rt.clients),
            )

    async def _barrer_lsp_ociosas(self, ttl: float) -> None:
        """Tarea de fondo: cada minuto evicta sesiones LSP sin uso hace más
        de `ttl`. La RAM escala con equipos ACTIVOS, no totales (una sesión
        LSP pesa cientos de MB; un equipo que editó 5 min y se fue no debe
        seguir reteniéndola). El re-arranque al volver degrada a
        tree-sitter mientras reindexa (net de capa 17): nunca se rompe.
        """
        while True:
            await asyncio.sleep(60)
            for tid, rt in list(self._runtimes.items()):
                ev = rt.evictar_lsp_ociosas(ttl)
                if ev:
                    logger.info(
                        "LSP evictadas por ociosas (%ds) equipo %s: %s",
                        int(ttl), tid, ", ".join(ev),
                    )

    async def run(self, host: str = "localhost", port: int = 8765) -> None:
        """Arranca el server WebSocket y lo deja escuchando para siempre."""
        # TTL GENEROSO a propósito (default 20 min): tan largo que evictar
        # implica casi seguro que el equipo se fue, no que está pensando.
        # Configurable por si el operador del VPS quiere ajustar RAM vs
        # latencia-de-reentrada. Pagar el reindex ocasional << retener
        # cientos de MB de equipos que ya no están.
        ttl = float(os.environ.get("LAIDEA_LSP_IDLE_SEC", "1200"))
        async with serve(self.handle, host, port):
            logger.info("servidor escuchando en ws://%s:%d", host, port)
            asyncio.create_task(self._barrer_lsp_ociosas(ttl))
            await asyncio.Future()
