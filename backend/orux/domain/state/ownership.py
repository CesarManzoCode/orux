"""Ownership: qué usuario es dueño de qué path.

Es el corazón de la tesis del producto: la colisión se previene con
coordinación (hay un dueño, su palabra manda sobre su zona), no se resuelve
fusionando después.

Capa 7: el dueño ahora es un **usuario real** (autenticado, normalizado), no
un `client_id` efímero. Y por eso ahora SÍ tiene sentido **persistir** el
ownership: "la clase Usuario es de joaquin" sobrevive a reiniciar el server y
a que joaquin se reconecte desde otro navegador. Mismo patrón de inyección
que `DiskStorage`/`UserStore`: recibe la ruta de un JSON; sin ruta (tests) es
en memoria. Ya NO se libera al desconectar: el dueño lo sigue siendo aunque
cierre la pestaña (lo recupera al volver a entrar como el mismo usuario).

Hardening (auditoría):
- BACKEND-AUDIT-0064: tmp único con pid+uuid para no chocar entre corutinas.
- BACKEND-AUDIT-0063: JSON no-dict se rechaza al cargar (no deja `_owners`
  como lista/None/int).
- BACKEND-AUDIT-0066: paths peligrosos al cargar se filtran con `path_seguro`.
- BACKEND-AUDIT-0097: try/except + rollback en memoria si write falla.
- BACKEND-AUDIT-0096: dump con `indent=2`+`sort_keys` para diagnóstico.
- BACKEND-AUDIT-0088: lock interno para que claim/asignar/liberar/reset sean
  atómicos sin depender del lock externo de SyncServer.
- BACKEND-AUDIT-0100: `purgar_usuario(u)` quita los archivos del usuario
  cuando se borra (todavía no se llama desde el admin, expuesto para que
  cuando ese flujo aparezca sea trivial cablearlo).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from .paths import path_seguro


class Ownership:
    def __init__(self, path: Path | str | None = None) -> None:
        # path de archivo -> usuario dueño. Un path que no está en el mapa
        # simplemente no tiene dueño (cualquiera lo edita y se aplica directo).
        self._owners: dict[str, str] = {}
        # Persistencia opcional. None = en memoria (tests, igual que el resto
        # del stack). Con ruta, el mapa sobrevive a reiniciar el server.
        self._path = Path(path) if path is not None else None
        # Lock interno: claim/asignar/liberar/reset son cortos pero deben
        # serializarse entre corutinas para no perder writes (BACKEND-AUDIT-0088).
        # threading.Lock porque las llamadas vienen indirectamente (no son
        # `async def`); el lock protege la mutación + persistencia.
        self._lock = threading.Lock()
        if self._path is not None and self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (ValueError, OSError, TypeError):
                data = {}
            # Validación estructural (BACKEND-AUDIT-0063): solo aceptamos
            # un dict con claves+valores string. Y solo paths que pasen
            # `path_seguro` (BACKEND-AUDIT-0066): si un attacker o una
            # versión vieja inyectó `../evil.py`, NO lo levantamos.
            if isinstance(data, dict):
                self._owners = {
                    k: v for k, v in data.items()
                    if isinstance(k, str) and isinstance(v, str) and path_seguro(k)
                }

    def _guardar(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atómico + único: tmp con pid+uuid para no pisarse con otra corutina
        # del mismo proceso (BACKEND-AUDIT-0064). Igual que DiskStorage.
        sufijo = f".{os.getpid()}.{uuid.uuid4().hex}.tmp"
        tmp = self._path.with_suffix(self._path.suffix + sufijo)
        try:
            # Permisos 0600: el ownership no tiene secretos pero es estado
            # autoritativo; no hay razón para exponerlo. Coherente con
            # users.json post-fix.
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._owners, f, indent=2, sort_keys=True,
                              ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                # Si write falla a mitad, limpia el tmp y propaga.
                try:
                    tmp.unlink()
                except OSError:
                    pass
                raise
            os.replace(tmp, self._path)
        except OSError:
            # Best-effort cleanup del tmp si quedó (BACKEND-AUDIT-0097); el
            # caller decide si rollback en memoria. Aquí solo propagamos.
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    def owner(self, path: str) -> str | None:
        """Quién es el dueño de `path`, o None si no tiene."""
        return self._owners.get(path)

    def claim(self, path: str, client_id: str) -> bool:
        """Intenta hacer dueño a `client_id` de `path`. Devuelve si quedó como dueño.

        Reglas mínimas: si no tiene dueño, lo reclama. Si ya eres el dueño, es
        idempotente (sigues siéndolo, True). Si lo tiene otro, no se lo quitas
        (False) — la coordinación no es robar la zona ajena. Transferir o
        soltar ownership a propósito sería otra pieza; no la necesita el flujo
        tentativo mínimo.
        """
        with self._lock:
            actual = self._owners.get(path)
            if actual is None:
                # Rollback en memoria si el persist falla (BACKEND-AUDIT-0097).
                self._owners[path] = client_id
                try:
                    self._guardar()
                except OSError:
                    del self._owners[path]
                    raise
                return True
            return actual == client_id

    def asignar(self, path: str, user: str) -> None:
        """Asigna `path` a `user` SIN condiciones. Persiste.

        Capa 12: lo usa el admin del workspace para repartir zonas (a
        diferencia de `claim`, no respeta al dueño actual). Sólo el server,
        tras verificar `UserStore.admin()`, llama esto; el modelo de datos
        en sí no sabe de permisos.
        """
        with self._lock:
            previo = self._owners.get(path)
            self._owners[path] = user
            try:
                self._guardar()
            except OSError:
                # Rollback al valor anterior si no se pudo persistir.
                if previo is None:
                    self._owners.pop(path, None)
                else:
                    self._owners[path] = previo
                raise

    def liberar(self, path: str) -> bool:
        """Quita el dueño de `path`. Devuelve si cambió.

        Lo usan dos flujos: (a) el server al borrar el archivo (un archivo
        que ya no existe no puede tener dueño); (b) el admin para revocar
        ownership explícitamente (panel admin → `AdminAssignMessage` con
        `username=""`). Persiste el mapa nuevo.
        """
        with self._lock:
            if path in self._owners:
                previo = self._owners[path]
                del self._owners[path]
                try:
                    self._guardar()
                except OSError:
                    self._owners[path] = previo
                    raise
                return True
            return False

    def purgar_usuario(self, user: str) -> int:
        """Quita TODOS los archivos cuyo dueño es `user`. Devuelve cuántos.

        Para cuando un admin borra una cuenta: si no liberamos los paths,
        quedan "bloqueados" — nadie es dueño activo pero el ownership los
        marca como ajenos (BACKEND-AUDIT-0100). No la llama todavía nadie:
        expuesta para que cablearlo sea trivial cuando aparezca el flujo.
        """
        with self._lock:
            a_quitar = [p for p, u in self._owners.items() if u == user]
            if not a_quitar:
                return 0
            previo = dict(self._owners)
            for p in a_quitar:
                del self._owners[p]
            try:
                self._guardar()
            except OSError:
                self._owners = previo
                raise
            return len(a_quitar)

    def reset(self) -> None:
        """Borra TODO el ownership y lo persiste vacío.

        Para el clone (capa 10): el workspace pasó a ser otro repo; los dueños
        del proyecto anterior ya no significan nada. Empieza limpio.
        """
        with self._lock:
            previo = self._owners
            self._owners = {}
            try:
                self._guardar()
            except OSError:
                self._owners = previo
                raise

    def snapshot(self) -> dict[str, str]:
        """Copia del mapa completo. Es lo que viaja en `OwnershipMessage`."""
        return dict(self._owners)
