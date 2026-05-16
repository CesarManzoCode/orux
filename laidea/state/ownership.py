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
"""

from __future__ import annotations

import json
from pathlib import Path


class Ownership:
    def __init__(self, path: Path | str | None = None) -> None:
        # path de archivo -> usuario dueño. Un path que no está en el mapa
        # simplemente no tiene dueño (cualquiera lo edita y se aplica directo).
        self._owners: dict[str, str] = {}
        # Persistencia opcional. None = en memoria (tests, igual que el resto
        # del stack). Con ruta, el mapa sobrevive a reiniciar el server.
        self._path = Path(path) if path is not None else None
        if self._path is not None and self._path.exists():
            try:
                self._owners = json.loads(
                    self._path.read_text(encoding="utf-8")
                )
            except (ValueError, OSError):
                self._owners = {}

    def _guardar(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._owners), encoding="utf-8")

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
        actual = self._owners.get(path)
        if actual is None:
            self._owners[path] = client_id
            self._guardar()
            return True
        return actual == client_id

    def asignar(self, path: str, user: str) -> None:
        """Asigna `path` a `user` SIN condiciones. Persiste.

        Capa 12: es la acción del admin del workspace. A diferencia de
        `claim` (que respeta al dueño actual — la coordinación no roba zona
        ajena), aquí el admin SÍ puede reasignar: en un proyecto open source
        ya hecho, alguien con autoridad reparte las zonas desde un panel, que
        es justo lo que faltaba para soltárselo a un equipo real. Sólo el
        server, tras verificar que quien pide es `UserStore.admin()`, llama
        esto; el modelo de datos en sí no sabe de permisos.
        """
        self._owners[path] = user
        self._guardar()

    def liberar(self, path: str) -> bool:
        """Quita el dueño de `path` (se borró el archivo). Devuelve si cambió.

        Un archivo que ya no existe no puede tener dueño. Lo llama el servidor
        al borrar; persiste el mapa nuevo.
        """
        if path in self._owners:
            del self._owners[path]
            self._guardar()
            return True
        return False

    def reset(self) -> None:
        """Borra TODO el ownership y lo persiste vacío.

        Para el clone (capa 10): el workspace pasó a ser otro repo; los dueños
        del proyecto anterior ya no significan nada. Empieza limpio.
        """
        self._owners = {}
        self._guardar()

    def snapshot(self) -> dict[str, str]:
        """Copia del mapa completo. Es lo que viaja en `OwnershipMessage`."""
        return dict(self._owners)
