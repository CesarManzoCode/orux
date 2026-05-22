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
from websockets.exceptions import ConnectionClosed

from ..analysis import impacto, motivos as motivos_de, tiers
from ..analysis.modelo import severidad_de
from ..analysis.lsp import arrancar_lsp
from ..analysis.tiers import lenguaje_de
from ..analysis.transitive import impacto_transitivo
from ..analysis.rename import (
    Rename,
    aplicar_rename,
    detectar_rename,
    texto_sugerencia,
)
from ..plans import limites, permite_rename
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
    path_seguro,
)
from ..teams import MemTeamStore, TeamError

logger = logging.getLogger(__name__)


# Topes y constantes de runtime ajustables por env (con clamp defensivo).
# Sin esto, un mensaje gigante (BACKEND-AUDIT-0222 / -0272) o un cliente que
# spamea pueden saturar el equipo entero. Los defaults son holgados.
def _env_int(name: str, default: int, minimo: int, maximo: int) -> int:
    try:
        v = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        v = default
    return max(minimo, min(maximo, v))


def _env_float(name: str, default: float, minimo: float, maximo: float) -> float:
    try:
        v = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        v = default
    return max(minimo, min(maximo, v))


# Tope HARD del frame WS recibido. websockets.serve() lo aplica antes de
# entregar el frame al handler — protege ANTES de `decode` (que también
# valida, defensa en profundidad).
WS_MAX_SIZE = _env_int("ORUX_WS_MAX_SIZE", 2 * 1024 * 1024, 64 * 1024, 16 * 1024 * 1024)
# Cola por conexión: cuántos frames sin leer se aceptan antes de cerrar.
WS_MAX_QUEUE = _env_int("ORUX_WS_MAX_QUEUE", 32, 4, 1024)
# Rate-limit por conexión: token bucket. Sin esto, un cliente puede saturar al
# equipo entero con miles de mensajes/s (BACKEND-AUDIT-0272). 50/s sostenido
# con burst 100 cubre tecleo humano agresivo + ráfagas legítimas (commit,
# admin_assign_many) y mata el spam.
RATE_TASA = _env_float("ORUX_RATE_PER_SEC", 50.0, 1.0, 1000.0)
RATE_BURST = _env_float("ORUX_RATE_BURST", 100.0, 1.0, 10_000.0)


class _RateLimiter:
    """Token bucket simple por conexión. No usa lock: cada conexión vive en
    una sola corutina, así que el acceso es serial. `permitir()` devuelve
    True si hay token; False si hay que tirar el mensaje."""

    __slots__ = ("_tokens", "_tasa", "_burst", "_t")

    def __init__(self, tasa: float, burst: float) -> None:
        self._tokens = float(burst)
        self._tasa = float(tasa)
        self._burst = float(burst)
        self._t = time.monotonic()

    def permitir(self) -> bool:
        ahora = time.monotonic()
        elapsed = ahora - self._t
        self._t = ahora
        self._tokens = min(self._burst, self._tokens + elapsed * self._tasa)
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


def _autor_git(usuario: str) -> tuple[str, str]:
    """Identidad de commit a partir del usuario autenticado (capa 7).

    Si el usuario parece un email lo usamos como email y el nombre es la
    parte antes de la @. Si no, nombre = usuario y email sintético
    `usuario@orux.local` (git exige un email; no tenemos uno real y no lo
    inventamos bonito a propósito — es honesto que sea sintético).
    """
    if "@" in usuario:
        return usuario.split("@", 1)[0], usuario
    return usuario, f"{usuario}@orux.local"


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

    async def usuarios(self) -> list[str]:
        """Lista de nombres registrados. Lo usa el cap de registro
        (BACKEND-AUDIT-0224)."""
        listar = getattr(self._b, "usuarios", None)
        return listar() if callable(listar) else []

    async def epoch(self, u: str) -> int:
        """Contador de sesiones del usuario (BACKEND-AUDIT-0002). 0 si el
        store no lo soporta (compat con stores legacy)."""
        ep = getattr(self._b, "epoch", None)
        if ep is None:
            return 0
        try:
            return int(ep(u))
        except (TypeError, ValueError):
            return 0


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
        # Robustez (auditoría C1/C2/A1/A2): serializa los tramos
        # read-modify-write del equipo (Update/Save/Resolve/Delete/Claim/
        # AdminAssign + el reinicio tras clone). Sin esto, dos handlers que
        # hacen "leo snapshot -> await (análisis en hilo / broadcast) ->
        # muto/difundo" se intercalan en el await y pisan estado con una
        # foto vieja (lost update en _propagar_rename; el `claim` del
        # creador corría DESPUÉS de un await; Resolve aceptaba contenido
        # obsoleto). Por-equipo: el de un equipo no frena al de otro. La
        # presencia (cursor) y git NO lo toman: siguen ágiles aunque un
        # análisis de Save esté corriendo. Trade-off aceptado: los Save de
        # UN equipo se serializan (son por Ctrl+S, no por tecla; la
        # coherencia del baseline lo exige).
        self._estado_lock = asyncio.Lock()

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


def _ip_cliente(websocket: ServerConnection) -> str:
    """IP del cliente. En el deploy la conexión TCP llega desde Caddy (mismo
    host), así que la IP real del usuario va en el header `X-Forwarded-For`
    que Caddy agrega al hacer de proxy. En dev/tests sin proxy se cae a la
    dirección del socket. Defensivo: ante cualquier fallo devuelve un
    placeholder — nunca rompe el flujo de autenticación."""
    try:
        req = getattr(websocket, "request", None)
        if req is not None:
            xff = req.headers.get("X-Forwarded-For", "")
            if xff:
                return xff.split(",")[0].strip()
    except Exception:
        pass
    try:
        addr = websocket.remote_address
        if addr:
            return str(addr[0])
    except Exception:
        pass
    return "desconocida"


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

    def _throttle(
        self, buckets: dict[str, list[float]], ip: str,
        tope: int, ventana: float,
    ) -> bool:
        """Ventana deslizante por IP: True = OK, False = la IP superó `tope`
        eventos en `ventana` segundos. Bucket por IP, limpieza perezosa.

        El GC del dict descarta buckets OBSOLETOS (vacíos, o cuyo registro
        más nuevo ya venció la ventana), no sólo los vacíos: si sólo borrara
        los vacíos, un atacante rotando >10k IPs con un goteo las mantiene
        no-vacías y el dict crecería sin control. Un bucket obsoleto es
        equivalente a uno ausente."""
        ahora = time.monotonic()
        corte = ahora - ventana
        bucket = buckets.setdefault(ip, [])
        bucket[:] = [t for t in bucket if t > corte]
        if len(bucket) >= tope:
            return False
        bucket.append(ahora)
        if len(buckets) > 10_000:
            for k in [
                k for k, v in buckets.items() if not v or v[-1] <= corte
            ]:
                buckets.pop(k, None)
        return True

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
        """
        rt.clients.discard(client)
        cid = rt._ids.pop(client, None)
        if cid is not None and rt._conns.get(cid) is client:
            rt._conns.pop(cid, None)
        if isinstance(exc, ConnectionClosed):
            logger.debug("cliente caído en equipo %s (envío)", rt.team_id)
        else:
            logger.warning(
                "envío falló en equipo %s, se descarta el cliente: %r",
                rt.team_id, exc,
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
        """Capa 6: avisa al dueño de cada archivo afectado por este cambio.

        Capa 26: `rename` (free) = se detectó un rename de miembro confiable
        pero el plan NO aplica el codemod; el aviso de ESE símbolo se
        reescribe al texto accionable ("se renombró X→Y, actualizá los
        usos"). `rename=None` => comportamiento byte-idéntico a capa 6/24
        (todos los tests previos siguen valiendo sin tocarse).

        "Sin clickear, lo hace solo" (README). Reglas: si el afectado no
        tiene dueño no hay a quién avisar; si no parsea, `impacto` da {} y
        no manda nada. Todo scopeado al workspace/ownership de ESTE equipo.

        Decisión del usuario: el aviso TAMBIÉN va al autor cuando el
        afectado le pertenece. Misma tesis aplicada de forma simétrica —
        si cambiar `Usuario` rompe `auth.py`, importa por igual sea quien
        sea el dueño de `auth.py`. El archivo origen del cambio ya queda
        fuera por `archivos_afectados` (filtra `o != path`), así que no
        hay auto-eco del archivo recién editado: solo OTROS archivos
        suyos donde el símbolo realmente se usa.
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

        # Capa 24 (rehecho): el camino DIRECTO (capas 17-21) corre SIEMPRE,
        # free y premium. Es el aviso de alto valor ("cambió la firma de X
        # → revisá las llamadas", severidad real). Antes premium hacía
        # `return` ANTES de esto y solo mandaba la onda transitiva: te dejaba
        # SIN el aviso bueno y encima mal etiquetado. Bug arreglado: premium
        # = free + cadena (la cadena se agrega DESPUÉS, sin reemplazar nada).
        def _analizar() -> tuple[dict, dict]:
            ses = rt.lsp_sesion(lenguaje_de(path), cap_langs)
            af = impacto(snap, path, viejo, nuevo, ses)
            if not af:
                return {}, {}
            return af, motivos_de(path, viejo, nuevo, ses)

        afectados, razones = await asyncio.to_thread(_analizar)
        if not afectados:
            return
        # Capa 26 (free): el cambio ES un rename confiable pero el plan no
        # lo aplica solo. Se cambia el "por qué" de ESE símbolo por el
        # qué-hacer concreto; el resto del aviso (a quién, byte-idéntico).
        if rename is not None and rename.clase in razones:
            razones = {**razones, rename.clase: texto_sugerencia(rename)}
        # Reagrupamos símbolo->archivos ==> archivo_afectado->símbolos.
        por_archivo: dict[str, list[str]] = {}
        for simbolo, archivos in afectados.items():
            for af in archivos:
                por_archivo.setdefault(af, []).append(simbolo)
        for af, simbolos in por_archivo.items():
            dueño = rt.ownership.owner(af)
            # El autor SÍ recibe aviso si el afectado le pertenece
            # (decisión del usuario): saber qué de tu propio código usa
            # lo que acabás de tocar es la misma tesis aplicada simétrica.
            if dueño is None:
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
                        severidades=[
                            severidad_de(razones.get(s, "")) for s in syms
                        ],
                    )
                ),
            )

        # --- Capa 24 (premium) = free + cadena -----------------------------
        # El directo de arriba YA se mandó (free y premium igual). Premium
        # AGREGA la onda por interfaz contaminada que llega MÁS ALLÁ del
        # directo. Decisión del usuario: se descartan (a) los hops
        # TERMINALES (uso en cuerpo: no se propaga, era ruido redundante con
        # el directo) y (b) los archivos que el directo YA cubrió (el
        # cliente deduplica por source+affected: un 2º mensaje los pisaría).
        # Resultado: premium NUNCA peor que free; la cadena solo suma valor.
        if limites(plan)["impacto"] != "transitivo":
            return
        directos = set(por_archivo)

        def _trans():
            lang = lenguaje_de(path)
            tier = tiers.tier_para(path)
            if tier is None or lang is None:
                return {}, False
            cambiados = list(tiers.cambios(path, viejo, nuevo))
            if not cambiados:
                return {}, False
            # Perf (capa 24c): índice de referencias 1 vez/análisis;
            # `extraer` memoizado por contenido (no D×N parseos).
            refs_idx = {
                f: tier.referencias(c)
                for f, c in snap.items()
                if lenguaje_de(f) == lang
            }

            def _fan(s: str, origen: str) -> set[str]:
                return {
                    f for f, r in refs_idx.items()
                    if f != origen and s in r
                }

            _cache: dict[str, dict] = {}

            def _extraer(c: str):
                if c not in _cache:
                    _cache[c] = tier.simbolos(c) or {}
                return _cache[c]

            return impacto_transitivo(
                snap, path, cambiados, fan_out=_fan,
                extraer=_extraer, lenguaje_de=lenguaje_de,
            )

        out, trunc = await asyncio.to_thread(_trans)
        sufijo = (
            " · análisis truncado (cambio muy amplio)" if trunc else ""
        )
        for af, items in out.items():
            if af in directos:
                continue  # ya lo cubrió el directo (no duplicar/pisar)
            dueño = rt.ownership.owner(af)
            # Misma simetría que el directo: el autor también recibe la
            # onda transitiva si el archivo aguas-abajo le pertenece.
            if dueño is None:
                continue
            # Solo la propagación REAL (interfaz contaminada). Terminal =
            # uso en cuerpo: no es la onda, es ruido (decisión del usuario).
            props = [d for d in items if not d["terminal"]]
            if not props:
                continue
            props.sort(key=lambda d: (d["cadena"][0], len(d["cadena"])))
            # Bug #2 arreglado: el encabezado nombra lo que REALMENTE
            # cambió (el símbolo ORIGEN de la cadena, que vive en
            # source_path), no el símbolo terminal. `cadena[0]` =
            # "<path>:<sym_original>" -> el sym es lo de después del último
            # ":" (los paths del workspace y los símbolos no llevan ":").
            syms = [d["cadena"][0].rsplit(":", 1)[1] for d in props]
            await self._enviar_a(
                rt,
                dueño,
                encode(
                    ImpactMessage(
                        source_path=path,
                        author_name=autor_nombre,
                        affected_path=af,
                        symbols=syms,
                        motivos=[d["motivo"] + sufijo for d in props],
                        severidades=[
                            severidad_de(d["motivo"]) for d in props
                        ],
                        cadena=props[0]["cadena"],
                    )
                ),
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
        """Capa 26 (premium): propaga un rename de miembro detectado a quien
        usa la clase, como **propuesta tentativa de capa 4 VERBATIM** — la
        misma ventana aprobar/rechazar que ya conocen. Cero UX/protocolo
        nuevo: la feature entra por la puerta que ya existe.

        Reusa el fan-out de capas 17-21 (`impacto`) para saber QUÉ archivos
        usan la clase de verdad: con sesión LSP viva es resolución real
        (mata falsos positivos); sin ella degrada a token-scan, igual que
        TODO el análisis. El dueño REVISA el diff y aprueba/rechaza: no es
        auto-commit a ciegas — la aprobación es la red de seguridad que
        hace seguro un codemod heurístico (la tesis trabajando a favor).
        """
        snap = rt.workspace.snapshot()
        plan = await self.teams.plan(rt.team_id)
        cap_langs = limites(plan)["max_langs"]

        def _afectados() -> dict[str, list[str]]:
            ses = rt.lsp_sesion(lenguaje_de(path), cap_langs)
            return impacto(snap, path, viejo, nuevo, ses)

        afectados = await asyncio.to_thread(_afectados)
        for af in afectados.get(ren.clase, []):
            if af == path:
                continue  # el origen ya tiene el rename (lo hizo el autor)
            contenido = snap.get(af)
            if contenido is None:
                continue
            propuesto = aplicar_rename(contenido, ren.viejo, ren.nuevo)
            if propuesto == contenido:
                continue  # el acceso no aparece textual acá: nada que hacer
            dueño = rt.ownership.owner(af)
            # Capa 26 (premium): el cambio lo construye el server (codemod
            # `aplicar_rename`), no lo tipeó nadie en ese archivo. El dueño
            # ve un autor explícito "OruxBot" para que la propuesta se lea
            # como "el sistema te propone esto" — misma ventana aprobar/
            # rechazar de capa 4, solo cambia quién aparece arriba. El
            # contexto del rename va en el mismo string (lo que cambió a lo
            # que pasa). `author_id` queda como el client_id real del que
            # disparó el rename: si el dueño rechaza, el revert (capa 4) le
            # llega a esa identidad y no a un id sintético sin conexión.
            etiqueta = f"OruxBot · rename {ren.viejo}→{ren.nuevo}"
            if dueño is None or dueño == autor_id:
                # Sin dueño o propio: se aplica directo (igual que un
                # update de capa 4 sin dueño). El baseline avanza: el
                # codemod ya es un punto coherente, no re-avisar sobre él.
                rt.workspace.update(af, propuesto)
                rt._analizado[af] = propuesto
                await self._broadcast_todos(
                    rt, encode(UpdateMessage(path=af, content=propuesto))
                )
            else:
                # Dueño ajeno: propuesta capa 4 VERBATIM. La etiqueta lleva
                # el contexto -> el dueño ve "Ana · rename x→y propone
                # cambios a af" + el diff, con la MISMA UI de siempre.
                prop = rt.proposals.put(
                    path=af,
                    author_id=autor_id,
                    author_name=etiqueta,
                    content=propuesto,
                )
                await self._enviar_a(
                    rt, dueño, encode(ProposalMessage(proposal=prop))
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

    async def _autenticar(self, websocket: ServerConnection) -> str | None:
        """Compuerta de la capa 7: nada de app hasta autenticarse.

        Lee mensajes hasta que uno autentique (register/login/session) y
        devuelve el usuario normalizado. Mientras no lo logre responde
        `auth_error` y sigue escuchando en la MISMA conexión. None si la
        conexión se cierra sin autenticarse.

        Robustez (auditoría seguridad A1): la compuerta es la única
        superficie de fuerza bruta / DoS de almacenamiento. PBKDF2 240k
        limita el rate pero no lo impide. Defensa por-conexión (sin store
        compartido — eso sería otra capa): cada fallo suma un backoff
        creciente ANTES de volver a escuchar (un atacante que prueba miles
        de contraseñas sobre UN socket se vuelve lentísimo), y pasado un
        tope de fallos se corta el socket (lo obliga a re-hacer el handshake
        TCP/WS cada N intentos — fricción real, sin castigar al usuario que
        se equivoca un par de veces). El register exitoso retorna ya: el
        tope de fallos también acota el DoS de cuentas basura por conexión.
        """
        fallos = 0
        # Tan alto que un humano que se equivoca tecleando jamás lo alcanza,
        # tan bajo que el atacante re-paga el handshake muy seguido.
        MAX_FALLOS = 12

        async def _fallo(reason: str) -> bool:
            """Responde el error, aplica el backoff y dice si hay que cortar
            (tope alcanzado). El sleep va DESPUÉS de enviar el error: el
            cliente legítimo ve el mensaje al instante; el costo es del que
            sigue intentando."""
            nonlocal fallos
            fallos += 1
            await websocket.send(encode(AuthErrorMessage(reason=reason)))
            if fallos >= MAX_FALLOS:
                logger.warning(
                    "auth: %d fallos en una conexión, se corta", fallos
                )
                return True
            # Lineal y modesto (0.3s, 0.6s, ...) tope 3s: invisible para un
            # error humano aislado, asfixiante para miles automatizados.
            await asyncio.sleep(min(3.0, 0.3 * fallos))
            return False

        async for raw in websocket:
            try:
                msg = decode(raw)
            except ValueError:
                if await _fallo("mensaje inválido"):
                    return None
                continue
            if isinstance(msg, RegisterMessage):
                # Anti-abuso: tope de registros por IP en ventana deslizante.
                # El registro es público; el backoff por-conexión no frena un
                # bot que hace connect -> register en bucle. Ver
                # `_throttle_registro`.
                if not self._throttle_registro(_ip_cliente(websocket)):
                    logger.warning("registro: tope por IP alcanzado")
                    if await _fallo(
                        "demasiados registros desde tu red, esperá unos minutos"
                    ):
                        return None
                    continue
                # Cierre de registro tras N usuarios (BACKEND-AUDIT-0224).
                # Default 0 = sin tope (modo prototipo). En producción, el
                # operador setea ORUX_REGISTRO_CERRADO_TRAS=N para fijar el
                # primer N como cuentas legítimas y a partir de ahí solo se
                # entra por OAuth o invitación admin. NO mitiga el caso de
                # un atacante que se registra ANTES del admin real — eso
                # requiere bootstrap controlado (Day 0); el cierre evita la
                # segunda fase (atacante crea cuentas en serie post-bootstrap).
                cap = _env_int("ORUX_REGISTRO_CERRADO_TRAS", 0, 0, 1_000_000)
                if cap > 0:
                    listar = getattr(self.users, "usuarios", None)
                    if listar is not None:
                        try:
                            actuales = await listar() if inspect.iscoroutinefunction(listar) else listar()
                        except Exception:
                            actuales = []
                        if len(actuales) >= cap:
                            if await _fallo("registro cerrado"):
                                return None
                            continue
                try:
                    return await self.users.registrar(msg.username, msg.password)
                except ValueError as e:
                    # BACKEND-AUDIT-0004: 'ese usuario ya existe' filtra
                    # info de enumeración. Detrás de un registro abierto el
                    # atacante puede sondear cuentas. Reportamos un mensaje
                    # genérico EXCEPTO para errores de FORMATO (charset,
                    # longitud) que no filtran existencia y que el cliente
                    # legítimo necesita para corregir su input.
                    motivo_real = str(e)
                    if "ya existe" in motivo_real.lower():
                        razon = "no se pudo registrar"
                    else:
                        razon = motivo_real
                    if await _fallo(razon):
                        return None
            elif isinstance(msg, LoginMessage):
                # Anti-fuerza-bruta: tope de logins por IP. El backoff
                # por-conexión se reinicia al reconectar; este tope no. Ver
                # `_throttle_login`.
                if not self._throttle_login(_ip_cliente(websocket)):
                    logger.warning("login: tope por IP alcanzado")
                    if await _fallo(
                        "demasiados intentos desde tu red, esperá unos minutos"
                    ):
                        return None
                    continue
                if await self.users.verificar(msg.username, msg.password):
                    return normalizar(msg.username)
                if await _fallo("usuario o contraseña incorrectos"):
                    return None
            elif isinstance(msg, SessionMessage):
                # Epoch del usuario al verificar: tokens emitidos antes de
                # revocar (cambio de pwd / logout-all) dejan de valer
                # quirúrgicamente sin tirar todas las sesiones del server
                # (BACKEND-AUDIT-0002).
                user = None
                try:
                    _ud = usuario_de_token(
                        msg.token, self._secret,
                        epoch_de=lambda u: 0,  # placeholder síncrono
                    )
                    if _ud is not None:
                        # Re-verifica el epoch contra el store async real.
                        epoch_actual = await self.users.epoch(_ud)
                        # Re-decodifica con un callable que devuelve el epoch
                        # ya consultado (un solo await; barato).
                        user = usuario_de_token(
                            msg.token, self._secret,
                            epoch_de=lambda u, _e=epoch_actual: _e,
                        )
                except Exception as e:
                    logger.warning("error verificando sesión: %s", e)
                if user is not None and await self.users.existe(user):
                    return user
                if await _fallo("sesión inválida, inicia sesión"):
                    return None
            else:
                if await _fallo("debes autenticarte primero"):
                    return None
        return None

    async def _lobby(
        self, websocket: ServerConnection, usuario: str
    ) -> str | None:
        """Compuerta de equipo (capa 15). Autenticado pero sin equipo: NO ve
        nada. Le mandamos sus equipos y esperamos que cree uno, redima un
        código, o elija uno suyo. Devuelve el team_id elegido, o None si la
        conexión se cierra sin elegir.

        Throttle (BACKEND-AUDIT-0218): mismo mecanismo que `_autenticar`. Un
        cliente que manda basura infinita en el lobby no debe consumir CPU/IO
        del server sin coste. MAX_FALLOS de mensajes inválidos cierra el socket.
        """
        async def _mandar_lobby(error: str = "") -> None:
            equipos = await self.teams.equipos_de(usuario)
            await websocket.send(
                encode(LobbyMessage(teams=equipos, error=error))
            )

        fallos = 0
        MAX_FALLOS = 16  # más holgado que auth (lobby tiene UX legítima de retry)

        async def _fallo(reason: str) -> bool:
            nonlocal fallos
            fallos += 1
            await _mandar_lobby(reason)
            if fallos >= MAX_FALLOS:
                logger.warning(
                    "lobby: %d fallos del usuario %s, se corta", fallos, usuario
                )
                return True
            await asyncio.sleep(min(2.0, 0.2 * fallos))
            return False

        await _mandar_lobby()
        async for raw in websocket:
            try:
                msg = decode(raw)
            except ValueError:
                if await _fallo("mensaje inválido"):
                    return None
                continue
            if isinstance(msg, CreateTeamMessage):
                try:
                    eq = await self.teams.crear_equipo(msg.nombre, usuario)
                    return eq["id"]
                except TeamError as e:
                    if await _fallo(str(e)):
                        return None
            elif isinstance(msg, RedeemInviteMessage):
                try:
                    eq = await self.teams.redimir(msg.code, usuario)
                except TeamError as e:
                    # Capa 22: tope de plan (equipo lleno). Mensaje de
                    # upgrade, NO "código inválido": el código sigue vivo.
                    if await _fallo(str(e)):
                        return None
                    continue
                if eq is not None:
                    return eq["id"]
                if await _fallo("código inválido o ya usado"):
                    return None
            elif isinstance(msg, SelectTeamMessage):
                if await self.teams.es_miembro(msg.team_id, usuario):
                    return msg.team_id
                if await _fallo("no sos miembro de ese equipo"):
                    return None
            else:
                # Cualquier mensaje de app antes de tener equipo: recordale
                # que primero hay que elegir/crear uno (la app sigue cerrada).
                if await _fallo("hay que crear/elegir equipo primero"):
                    return None
        return None

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

    async def _aplicar(
        self,
        rt: TeamRuntime,
        websocket: ServerConnection,
        yo,
        team_id: str,
        message,
    ) -> None:
        """Procesa UN mensaje ya decodificado de la sesion de equipo.

        Extraido del bucle (capa de robustez): aislado para que una
        excepcion aqui la capture el llamador y NO mate la conexion. El
        antiguo `continue` de capa 5 (rebote del lock) es ahora `return`:
        en un metodo, "saltar este mensaje" = volver. Cuando lo invoca
        `_despachar` para un mensaje que muta estado, corre bajo
        `rt._estado_lock` (los helpers que llama NO re-toman el lock: se
        adquiere una sola vez por mensaje, no es reentrante).
        """
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
                        return
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

                # Capa 26: ¿este checkpoint ES un rename de miembro
                # confiable? La detección usa los Simbolo del tier
                # (parseo) -> a un hilo (no bloquear el loop).
                def _det(b=base, a=actual, p=message.path):
                    t = tiers.tier_para(p)
                    if t is None:
                        return None
                    sa = t.simbolos(b)
                    sd = t.simbolos(a)
                    if sa is None or sd is None:
                        return None
                    return detectar_rename(sa, sd)

                ren = await asyncio.to_thread(_det)
                plan = await self.teams.plan(rt.team_id)
                if ren is not None and permite_rename(plan):
                    # Premium: se propaga como propuesta capa 4. El
                    # aviso genérico de ese símbolo lo reemplaza la
                    # propuesta accionable (no se manda además).
                    await self._propagar_rename(
                        rt, message.path, base, actual,
                        ren, yo.client_id, yo.name,
                    )
                else:
                    # Free (o sin rename): impacto normal; si hubo
                    # rename confiable, el "por qué" se vuelve el
                    # texto accionable (premium lo aplica por vos).
                    await self._notificar_impacto(
                        rt, message.path, base, actual,
                        yo.client_id, yo.name, rename=ren,
                    )
        elif isinstance(message, DeleteMessage):
            # Sólo borra el dueño, o cualquiera si no tiene dueño.
            dueño = rt.ownership.owner(message.path)
            if dueño is None or dueño == yo.client_id:
                if rt.workspace.delete(message.path):
                    logger.info(
                        "delete: %s borró %r en equipo %s",
                        yo.client_id, message.path, team_id,
                    )
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
                        # Robustez M1: filtrá path-a-path (no el reparto
                        # entero) — un path inseguro en la lista no debe
                        # meter ownership fantasma ni anular el resto.
                        if not path_seguro(p):
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
                # Destructivo: reemplaza el workspace del equipo entero.
                # En producción tiene que quedar auditado quién y de dónde.
                logger.info(
                    "clone (DESTRUCTIVO) pedido por %s en equipo %s",
                    yo.client_id, team_id,
                )
                async with rt._git_lock:
                    ok, detalle = await asyncio.to_thread(
                        rt.git.clonar,
                        message.url, message.username, message.token,
                    )
                    if ok:
                        # El clone reemplaza TODO el workspace/ownership:
                        # tomá también el lock de estado para que un Update
                        # concurrente no aplique sobre el árbol viejo justo
                        # mientras se reinicia. Orden git->estado (nunca al
                        # revés en ningún handler) => sin deadlock.
                        async with rt._estado_lock:
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
                # seguro: force-with-lease + PR; orux es su único
                # escritor). Cualquier otra (p.ej. main) = push
                # normal SIN forzar (capa 10: non-ff honesto, jamás
                # pisa historia compartida). orux decide force-o-no
                # por el destino; el usuario solo elige a dónde.
                rama_eq = f"orux/{rt.team_id}"
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
        async with serve(
            self.handle, host, port,
            max_size=WS_MAX_SIZE, max_queue=WS_MAX_QUEUE,
        ):
            logger.info(
                "servidor escuchando en ws://%s:%d (max_size=%d max_queue=%d)",
                host, port, WS_MAX_SIZE, WS_MAX_QUEUE,
            )
            asyncio.create_task(self._barrer_lsp_ociosas(ttl))
            await asyncio.Future()
