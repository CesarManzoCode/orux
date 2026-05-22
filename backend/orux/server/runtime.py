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
import threading
import time

from websockets.asyncio.server import ServerConnection

from ..analysis.lsp import arrancar_lsp
from ..git import GitRepo
from ..state import DiskStorage, Ownership, Proposals, Roster, Workspace


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
