"""Propuestas pendientes: cambios tentativos esperando que el dueño resuelva.

Cuando alguien que no es el dueño edita un archivo con dueño, su cambio no se
aplica: se guarda aquí como una `Proposal` hasta que el dueño la apruebe o la
rechace. Es el "editar primero, negociar después, aplicar al final" hecho
estado.

Decisiones:

- **Una propuesta por (archivo, autor), no por pulsación.** El `id` es
  determinista (`path::author_id`, lo arma el servidor). Mientras el autor
  sigue tecleando, su propuesta se reemplaza con el último contenido en vez de
  acumular una propuesta por tecla. El dueño siempre ve la versión más reciente.

- **Sin cola para dueños desconectados.** Si el dueño no está conectado cuando
  se crea la propuesta, el aviso se pierde (el servidor no lo encuentra para
  enviárselo). La propuesta igual queda guardada aquí, pero no hay reentrega al
  reconectar: eso sería otra pieza (notificaciones durables) y no la necesita el
  flujo mínimo. Anotado a propósito como límite conocido del prototipo.
"""

from __future__ import annotations

from ..protocol import Proposal


class Proposals:
    def __init__(self) -> None:
        # id (path::author_id) -> Proposal. El id determinista es lo que hace
        # que reeditar reemplace en vez de duplicar.
        self._pendientes: dict[str, Proposal] = {}

    @staticmethod
    def make_id(path: str, author_id: str) -> str:
        return f"{path}::{author_id}"

    def put(self, path: str, author_id: str, author_name: str, content: str) -> Proposal:
        """Registra (o reemplaza) la propuesta de `author_id` sobre `path`."""
        pid = self.make_id(path, author_id)
        prop = Proposal(
            id=pid,
            path=path,
            author_id=author_id,
            author_name=author_name,
            content=content,
        )
        self._pendientes[pid] = prop
        return prop

    def get(self, proposal_id: str) -> Proposal | None:
        return self._pendientes.get(proposal_id)

    def pop(self, proposal_id: str) -> Proposal | None:
        """Saca la propuesta (al resolverla). None si ya no estaba."""
        return self._pendientes.pop(proposal_id, None)

    def drop_author(self, author_id: str) -> None:
        """Descarta las propuestas de un autor (se desconectó): ya son moot."""
        self._pendientes = {
            pid: p for pid, p in self._pendientes.items() if p.author_id != author_id
        }

    def drop_path(self, path: str) -> None:
        """Descarta las propuestas sobre `path` (se borró el archivo): moot."""
        self._pendientes = {
            pid: p for pid, p in self._pendientes.items() if p.path != path
        }
