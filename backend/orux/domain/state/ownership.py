"""Ownership: qué usuario es dueño de qué path. Memoria pura.

Es el corazón de la tesis del producto: la colisión se previene con
coordinación (hay un dueño, su palabra manda sobre su zona), no se resuelve
fusionando después.

Capa 7: el dueño es un **usuario real** (autenticado, normalizado), no
un `client_id` efímero. El ownership sobrevive a reiniciar el server y
a que el dueño se reconecte desde otro navegador.

Refactor hex: este módulo es PURO MEMORIA. La persistencia vive afuera vía
`OwnershipStorePort` (`adapters.json.JsonOwnershipStore` en dev,
`db.stores.PgOwnershipStore` en producción). El caller (TeamRuntime /
SyncServer) hidrata al abrir el equipo (`Ownership(inicial=...)`) y persiste
tras cada mutación (`await store.guardar(team_id, ownership.snapshot())`).
Antes esta clase manejaba un JSON inline opcional; ese código vive ahora en
`JsonOwnershipStore` con la misma semántica y hardening (atomicidad,
permisos 0600, validación con path_seguro).

El lock interno se mantiene: `claim`/`asignar`/`liberar`/`reset` son cortos
pero deben serializarse entre corutinas para no perder writes. La
persistencia (cuando aplica) la dispara el caller después de mutar; si
fallar, el caller decide rollback (en la práctica, el flujo write-through
trata un error de persistencia como warning loggeado, no rollback en
memoria — el siguiente guardar exitoso pisa).
"""

from __future__ import annotations

import threading


class Ownership:
    def __init__(self, inicial: dict[str, str] | None = None) -> None:
        # path de archivo -> usuario dueño. Hidratación opcional desde un
        # snapshot externo (el caller hace `await store.cargar(team_id)`
        # antes de construir el runtime).
        self._owners: dict[str, str] = dict(inicial) if inicial else {}
        # Serializa mutaciones entre corutinas: el dispatch corre en el
        # loop asyncio pero los métodos son sync; el lock evita writes
        # cruzados entre `claim` y `asignar` concurrentes.
        self._lock = threading.Lock()

    def owner(self, path: str) -> str | None:
        """Quién es el dueño de `path`, o None si no tiene."""
        return self._owners.get(path)

    def claim(self, path: str, client_id: str) -> bool:
        """Intenta hacer dueño a `client_id` de `path`. Devuelve si quedó como dueño.

        Reglas: si no tiene dueño, lo reclama. Si ya eres el dueño, es
        idempotente (sigues siéndolo, True). Si lo tiene otro, no se lo
        quitas (False) — la coordinación no es robar la zona ajena.
        """
        with self._lock:
            actual = self._owners.get(path)
            if actual is None:
                self._owners[path] = client_id
                return True
            return actual == client_id

    def asignar(self, path: str, user: str) -> None:
        """Asigna `path` a `user` SIN condiciones.

        Capa 12: lo usa el admin del workspace para repartir zonas (a
        diferencia de `claim`, no respeta al dueño actual). Sólo el server,
        tras verificar el rol del equipo, llama esto; el modelo de datos
        en sí no sabe de permisos.
        """
        with self._lock:
            self._owners[path] = user

    def liberar(self, path: str) -> bool:
        """Quita el dueño de `path`. Devuelve si cambió.

        Lo usan dos flujos: (a) el server al borrar el archivo (un archivo
        que ya no existe no puede tener dueño); (b) el admin para revocar
        ownership explícitamente.
        """
        with self._lock:
            if path in self._owners:
                del self._owners[path]
                return True
            return False

    def purgar_usuario(self, user: str) -> int:
        """Quita TODOS los archivos cuyo dueño es `user`. Devuelve cuántos.

        Para cuando un admin borra una cuenta: si no liberamos los paths,
        quedan "bloqueados" — nadie es dueño activo pero el ownership los
        marca como ajenos.
        """
        with self._lock:
            a_quitar = [p for p, u in self._owners.items() if u == user]
            for p in a_quitar:
                del self._owners[p]
            return len(a_quitar)

    def reset(self) -> None:
        """Borra TODO el ownership.

        Para el clone (capa 10): el workspace pasó a ser otro repo; los dueños
        del proyecto anterior ya no significan nada. Empieza limpio.
        """
        with self._lock:
            self._owners = {}

    def snapshot(self) -> dict[str, str]:
        """Copia del mapa completo. Es lo que el caller persiste vía
        `OwnershipStorePort.guardar(team_id, snapshot)` y lo que viaja en
        `OwnershipMessage`."""
        return dict(self._owners)
