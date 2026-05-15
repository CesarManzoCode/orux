"""Ownership: qué cliente es dueño de qué path.

Es el corazón de la tesis del producto: la colisión se previene con
coordinación (hay un dueño, su palabra manda sobre su zona), no se resuelve
fusionando después. Esta capa es la versión mínima de eso a nivel de archivo
completo; la granularidad por zona/línea y la prevención de colisiones
concurrentes son la capa 5, aparte.

Decisiones de prototipo (a documentar porque no son obvias y se van a revisar
cuando llegue auth):

- **El ownership es efímero, por sesión.** Vive en memoria, no se persiste. En
  el producto el ownership es durable e invisible ("la clase User es de
  Joaquín"). Aquí, sin identidad estable ni auth, persistirlo no tendría
  sentido: el `client_id` cambia en cada reconexión.

- **Se libera al desconectar (lo hace el servidor, no esta clase).** Si el
  dueño se va y su path sigue marcado como suyo, nadie podría editarlo de
  verdad (todo cambio sería tentativo y no habría dueño conectado para
  aprobarlo): deadlock. Liberar al desconectar evita ese estado muerto en el
  prototipo. El ownership real no se liberará así.
"""

from __future__ import annotations


class Ownership:
    def __init__(self) -> None:
        # path -> client_id del dueño. Un path que no está en el mapa
        # simplemente no tiene dueño (cualquiera lo edita y se aplica directo).
        self._owners: dict[str, str] = {}

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
            return True
        return actual == client_id

    def release_all(self, client_id: str) -> bool:
        """Suelta todos los paths que poseía `client_id` (se desconectó).

        Devuelve True si algo cambió, para que el servidor sepa si tiene que
        volver a difundir el mapa.
        """
        antes = len(self._owners)
        self._owners = {
            p: c for p, c in self._owners.items() if c != client_id
        }
        return len(self._owners) != antes

    def snapshot(self) -> dict[str, str]:
        """Copia del mapa completo. Es lo que viaja en `OwnershipMessage`."""
        return dict(self._owners)
