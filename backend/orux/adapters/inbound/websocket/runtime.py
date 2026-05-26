"""`TeamRuntime`: todo el estado vivo de UN equipo.

Hasta capa 14 había UN workspace global. Desde capa 15 cada equipo tiene su
propio runtime — workspace, presencia, ownership, propuestas, repo git,
sesiones LSP y conexiones — y nada cruza de un equipo a otro. Esta clase es
ese contenedor; `SyncServer` (en `sync.py`) crea una instancia por equipo,
perezosamente, y opera siempre sobre el runtime del equipo de la conexión.

Se separó de `sync.py` porque es una pieza de estado cohesiva y autónoma: no
sabe de WebSockets ni del protocolo, solo guarda el estado de un equipo y
gestiona el ciclo de vida de sus sesiones LSP.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from websockets.asyncio.server import ServerConnection

from orux.analysis.lsp import arrancar_lsp
from orux.ports import GitPort, WorkspaceStoragePort
from orux.state import Ownership, Proposals, Roster, Workspace

logger = logging.getLogger(__name__)


class _LspEstado:
    """Estado por lenguaje de un equipo: sesión viva, o cooldown tras
    fallo. Antes el cache era `dict[str, SesionLSP | None]` y un None
    quedaba GRABADO para siempre — si pyright no arrancaba una vez (env
    sin libatomic, OOM, lo que sea), la degradación era permanente hasta
    reciclar el LSP entero. Y si la sesión MORÍA después (subprocess
    crash), la cache devolvía un objeto muerto y todas las llamadas
    fallaban silenciosas. Este pequeño contenedor hace ambos casos
    auto-recuperables.
    """

    def __init__(self) -> None:
        self.sesion = None  # SesionLSP | None
        self.ultimo_fallo: float = 0.0
        self.intentos_fallidos: int = 0

    def cooldown_seg(self) -> float:
        """Backoff exponencial entre reintentos: 60s, 120s, 240s, ..., tope
        en 1800s (30 min). El tope evita pelotear el spawn de pyright cada
        análisis cuando el entorno está roto de raíz; permitir reintento
        para auto-recuperar cuando se arregla."""
        if self.intentos_fallidos <= 0:
            return 0.0
        return min(1800.0, 60.0 * (2 ** (self.intentos_fallidos - 1)))

    def puede_reintentar(self, ahora: float) -> bool:
        return ahora - self.ultimo_fallo >= self.cooldown_seg()


class TeamRuntime:
    """Todo el estado vivo de UN equipo: su workspace, presencia, ownership,
    propuestas, repo git y conexiones. Un equipo no ve al otro porque cada
    uno tiene su runtime y los broadcasts se hacen sobre `rt.clients`.
    """

    def __init__(
        self,
        team_id: str = "",
        storage: WorkspaceStoragePort | None = None,
        ownership: Ownership | None = None,
        git: GitPort | None = None,
    ) -> None:
        self.team_id = team_id
        # Propagamos team_id al Workspace para que los logs de
        # persistencia (`update`/`delete`) lo incluyan; sin esto, en un
        # host multi-equipo es imposible saber QUÉ equipo tuvo el fallo.
        self.workspace = Workspace(storage=storage, team_id=team_id)
        self.workspace.cargar_de_disco()
        # Capa 17: dir del workspace en disco = rootUri de pyright. Sólo el
        # adapter `DiskStorage` expone `.root`; otros adapters del
        # WorkspaceStoragePort (cuando existan) podrían no tenerlo y el LSP
        # queda apagado para ese equipo (degrada a tree-sitter/coarse, igual
        # que tests sin storage). El sandbox sigue verde.
        self._ws_dir = (
            str(storage.root) if storage is not None
            and hasattr(storage, "root") else None
        )
        # Capa 18: una sesión LSP POR LENGUAJE ("py"->pyright,
        # "jsts"->tsserver). Lazy: se arranca al 1er análisis de ESE
        # lenguaje. Antes cacheaba `None` para siempre tras un fallo;
        # ahora cada entrada es un `_LspEstado` que sabe (a) si la sesión
        # cacheada murió (detectable vía `disponible()`), (b) si toca
        # reintentar arrancar tras el cooldown exponencial. Auto-recupera
        # de OOMs/segfaults y de un entorno que arregla el operador en
        # caliente, sin tener que evictar todo y reciclar.
        self._lsp: dict[str, _LspEstado] = {}
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
        # Eviction de runtimes ociosos. El barrido evicta runtimes sin
        # conexiones desde hace > TTL. Sin esto, `SyncServer._runtimes`
        # crecía sin techo: cada equipo que se conectó alguna vez
        # retenía RAM (workspace + ownership + presencia + propuestas)
        # hasta que el proceso muriera. Marca: monotonic() cuando el
        # ÚLTIMO cliente se va; None cuando hay al menos uno conectado.
        # El runtime es perezoso por equipo: al volver alguien, se
        # rehidrata vía `_runtime_para` (ownership y propuestas desde
        # Postgres si hay store; sin store, modo dev — no evictamos
        # runtimes con propuestas pendientes para no perderlas).
        self._vacio_desde: float | None = time.monotonic()
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
        # AUDITORIA-SEGURIDAD 2026-05-25 A-WS-01: rate limit dedicado para
        # PresenceMessage POR cliente. Sin esto, un atacante autenticado
        # podía declarar presencia en TODAS las líneas de un archivo a
        # ~10/s (bajo el 50/s del rate limit global), ocupando
        # `lineas_ocupadas(path)` y rebotando edits legítimos -> DoS lógico
        # de la edición colaborativa. Bucket por client_id: una persona
        # mueve el cursor pocas veces por segundo; >5/s es spam programático.
        # Cleanup: las entradas se borran al desconectar el cliente
        # (en sync.py:_quitar_de_runtime / _evict_session).
        self._presence_t: dict[str, float] = {}  # client_id -> last seen (monotonic)
        self._presence_tokens: dict[str, float] = {}  # client_id -> tokens

    _PRESENCE_RATE = 5.0  # mensajes/seg sostenido
    _PRESENCE_BURST = 10.0  # ráfaga inicial

    def permitir_presence(self, client_id: str) -> bool:
        """Token bucket por cliente para PresenceMessage. True=OK, False=tirar.
        Sostenido 5/s con burst 10. Sin lock: cada conexión es una corutina
        única, los handlers no se intercalan a sí mismos."""
        ahora = time.monotonic()
        previo = self._presence_t.get(client_id, ahora)
        tokens = self._presence_tokens.get(client_id, self._PRESENCE_BURST)
        elapsed = max(0.0, ahora - previo)
        tokens = min(self._PRESENCE_BURST, tokens + elapsed * self._PRESENCE_RATE)
        self._presence_t[client_id] = ahora
        if tokens >= 1.0:
            self._presence_tokens[client_id] = tokens - 1.0
            return True
        self._presence_tokens[client_id] = tokens
        return False

    def olvidar_presence_cliente(self, client_id: str) -> None:
        """Borra el bucket de PresenceMessage al desconectar (evita fuga de
        memoria a largo plazo en runtimes de muchos clientes rotativos)."""
        self._presence_t.pop(client_id, None)
        self._presence_tokens.pop(client_id, None)

    def lsp_sesion(self, lang: str | None, cap_langs: float | None = None):
        """Sesión LSP de ESTE equipo para `lang`, tibia: se arranca UNA vez
        (lazy, en el 1er análisis de ese lenguaje) y se reusa. Llamar
        SIEMPRE desde un hilo worker (spawn+handshake es bloqueante). None
        si el lenguaje no tiene server / no hay dir / la sesión está en
        cooldown tras un fallo => degrada a capa 16.

        Reintento + detección de muerte (capa nueva): si la sesión
        cacheada murió (subprocess crash, OOM), se descarta y se reintenta
        arrancar; si arrancar falla, se aplica un cooldown exponencial
        (60s, 120s, 240s, ..., tope 30 min) antes del próximo intento. El
        operador puede arreglar el entorno (`apt install libatomic1`,
        liberar RAM) y el LSP vuelve solo sin tener que reciclar el
        equipo entero.

        Capa 22: `cap_langs` = tope de lenguajes LSP del plan del equipo.
        Si ya hay `cap_langs` lenguajes con sesión y este es NUEVO, NO se
        arranca (degrada a tree-sitter/coarse, no rompe). Es el lever de
        costo real: premium = sin tope. El cap lo precomputa el server en
        el loop (el plan vive en un store async); acá solo se aplica.
        """
        if lang is None or self._ws_dir is None:
            return None
        with self._lsp_lock:
            ahora = time.monotonic()
            estado = self._lsp.get(lang)

            # Caso A: tenemos una sesión cacheada.
            if estado is not None and estado.sesion is not None:
                if estado.sesion.disponible():
                    self._lsp_uso[lang] = ahora
                    return estado.sesion
                # Subprocess murió silenciosamente: limpiarlo y caer
                # abajo a la lógica de re-arranque con cooldown.
                logger.warning(
                    "LSP %s murió (subprocess) en equipo %s, reintentando",
                    lang, self.team_id,
                )
                try:
                    estado.sesion.cerrar()
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "error cerrando LSP %s muerto en equipo %s: %r",
                        lang, self.team_id, e,
                    )
                estado.sesion = None

            # Caso B: en cooldown tras fallo previo, no insistir.
            if estado is not None and not estado.puede_reintentar(ahora):
                return None

            # Caso C: tope del plan — solo aplica a lenguajes NUEVOS
            # (sin estado todavía). Si ya teníamos estado, este lang ya
            # contó alguna vez; no lo bloqueamos por venir de un fallo.
            if (
                cap_langs is not None and estado is None
                and self._lsp_lenguajes_activos() >= cap_langs
            ):
                return None

            # Reintentar / arrancar por primera vez.
            nueva = arrancar_lsp(lang, self._ws_dir)
            if estado is None:
                estado = _LspEstado()
                self._lsp[lang] = estado
            if nueva is not None:
                if estado.intentos_fallidos > 0:
                    logger.info(
                        "LSP %s re-arrancado en equipo %s tras %d fallo(s)",
                        lang, self.team_id, estado.intentos_fallidos,
                    )
                estado.sesion = nueva
                estado.intentos_fallidos = 0
                estado.ultimo_fallo = 0.0
                self._lsp_uso[lang] = ahora
                return nueva
            # Falló (arrancar_lsp ya logueó el porqué exacto). Marca
            # fallo + cooldown crecente.
            estado.intentos_fallidos += 1
            estado.ultimo_fallo = ahora
            logger.warning(
                "LSP %s arranque #%d falló en equipo %s; "
                "próximo reintento en %ds",
                lang, estado.intentos_fallidos, self.team_id,
                int(estado.cooldown_seg()),
            )
            return None

    def _lsp_lenguajes_activos(self) -> int:
        """Cantidad de lenguajes con sesión LSP VIVA. Cooldowns no
        cuentan para el cap del plan (no hay sesión consumiendo RAM)."""
        return sum(
            1 for e in self._lsp.values()
            if e.sesion is not None and e.sesion.disponible()
        )

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
                estado = self._lsp[lang]
                if ahora - self._lsp_uso.get(lang, ahora) < ttl:
                    continue
                if estado.sesion is not None:
                    try:
                        estado.sesion.cerrar()
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "error cerrando LSP %s ociosa en equipo %s: %r",
                            lang, self.team_id, e,
                        )
                del self._lsp[lang]
                self._lsp_uso.pop(lang, None)
                evictadas.append(lang)
        return evictadas

    def reciclar_lsp(self) -> None:
        """Mata TODAS las sesiones y fuerza re-arranque al próximo análisis.
        Para el reinicio de capa 15 (clone destructivo cambia TODO el
        workspace: el índice de cada server quedó obsoleto)."""
        with self._lsp_lock:
            for lang, estado in self._lsp.items():
                if estado.sesion is not None:
                    try:
                        estado.sesion.cerrar()
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "error cerrando LSP %s al reciclar (equipo %s): %r",
                            lang, self.team_id, e,
                        )
            self._lsp = {}
            self._lsp_uso = {}
