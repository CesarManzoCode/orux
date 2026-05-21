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

- **Reentrega al dueño que se conecta.** Si el dueño no estaba en línea cuando
  se creó la propuesta (o se desconectó antes de resolverla), la propuesta NO
  se pierde: queda guardada acá y el servidor se la re-emite al final del
  handshake cuando vuelve. Ese re-envío usa `por_dueño(...)` para filtrar las
  que apuntan a archivos que hoy le pertenecen. (Antes era un "límite conocido"
  documentado; al usarlo con devs reales se vio que rompe la tesis — un cambio
  invisible NO es seguro — así que ahora hay reentrega de verdad.)

- **Topes por autor + por contenido** (BACKEND-AUDIT-0071, -0238). Un atacante
  con cuenta puede mantener N propuestas grandes en memoria. Topamos por
  (a) tamaño individual del `content` (alineado con `protocol.MAX_FRAME_BYTES`),
  (b) cantidad total por autor por equipo. Cuando se rebasa, se rechaza la
  PUT más nueva — el autor tiene que resolver/abandonar las viejas primero.
"""

from __future__ import annotations

from ..protocol import Proposal

# Tope de tamaño de `content` por propuesta. Alineado con el `content` de
# `UpdateMessage`: una propuesta NO es más grande que un update legítimo
# (en el flujo, una propuesta ES el contenido propuesto del archivo).
MAX_CONTENT_BYTES = 1024 * 1024  # 1 MB

# Tope de propuestas por autor por equipo. 50 archivos abiertos en paralelo
# es muy holgado; 10 era restrictivo. Sin el tope, un autor podía crecer la
# tabla sin techo (BACKEND-AUDIT-0238).
MAX_POR_AUTOR = 50


class PropuestaInvalida(ValueError):
    """La propuesta excede los topes o tiene tipos inválidos. El server la
    trata como mensaje malo y opcionalmente avisa al autor."""


class Proposals:
    def __init__(self) -> None:
        # id (path::author_id) -> Proposal. El id determinista es lo que hace
        # que reeditar reemplace en vez de duplicar.
        self._pendientes: dict[str, Proposal] = {}
        # Índice secundario author_id -> set(pid) para no recorrer todo en
        # drop_author. Lo mantenemos coherente con `_pendientes`.
        self._por_autor: dict[str, set[str]] = {}

    @staticmethod
    def make_id(path: str, author_id: str) -> str:
        return f"{path}::{author_id}"

    def put(self, path: str, author_id: str, author_name: str, content: str) -> Proposal:
        """Registra (o reemplaza) la propuesta de `author_id` sobre `path`.

        Levanta `PropuestaInvalida` si:
        - los tipos no cuadran (BACKEND-AUDIT-0101);
        - el `content` excede `MAX_CONTENT_BYTES` (BACKEND-AUDIT-0238);
        - el autor ya tiene `MAX_POR_AUTOR` propuestas distintas y esta es
          una NUEVA (no un reemplazo de una ya existente sobre el mismo path).
        """
        if not isinstance(path, str) or not path:
            raise PropuestaInvalida("path inválido")
        if not isinstance(author_id, str) or not author_id:
            raise PropuestaInvalida("author_id inválido")
        if not isinstance(author_name, str):
            raise PropuestaInvalida("author_name inválido")
        if not isinstance(content, str):
            raise PropuestaInvalida("content inválido")
        if len(content) > MAX_CONTENT_BYTES:
            raise PropuestaInvalida(
                f"propuesta demasiado grande ({len(content)} > {MAX_CONTENT_BYTES})"
            )
        pid = self.make_id(path, author_id)
        propias = self._por_autor.get(author_id, set())
        # Si NO es reemplazo y el autor ya está en el tope, rechazar.
        if pid not in propias and len(propias) >= MAX_POR_AUTOR:
            raise PropuestaInvalida(
                f"demasiadas propuestas pendientes (>{MAX_POR_AUTOR}); "
                f"resolvé o abandoná las viejas"
            )
        prop = Proposal(
            id=pid,
            path=path,
            author_id=author_id,
            author_name=author_name,
            content=content,
        )
        self._pendientes[pid] = prop
        self._por_autor.setdefault(author_id, set()).add(pid)
        return prop

    def get(self, proposal_id: str) -> Proposal | None:
        return self._pendientes.get(proposal_id)

    def pop(self, proposal_id: str) -> Proposal | None:
        """Saca la propuesta (al resolverla). None si ya no estaba."""
        prop = self._pendientes.pop(proposal_id, None)
        if prop is not None:
            propias = self._por_autor.get(prop.author_id)
            if propias is not None:
                propias.discard(proposal_id)
                if not propias:
                    del self._por_autor[prop.author_id]
        return prop

    def drop_author(self, author_id: str) -> None:
        """Descarta las propuestas de un autor (se desconectó): ya son moot.

        O(k) sobre el set indexado, no O(N) sobre todas (BACKEND-AUDIT-0081)."""
        for pid in self._por_autor.pop(author_id, set()):
            self._pendientes.pop(pid, None)

    def para(self, owner_id: str, owner_de) -> list[Proposal]:
        """Propuestas cuyo path le pertenece HOY a `owner_id`. El callable
        `owner_de(path) -> client_id | None` viene de Ownership: lo recibimos
        en vez de importarlo para no acoplar al revés (Proposals no sabe del
        módulo de ownership). Lo usa el server al final del handshake para
        re-entregarle al dueño las que se acumularon mientras no estaba.
        Nota: filtra por dueño ACTUAL (si el admin reasignó el archivo, la
        propuesta le sale al nuevo dueño, no al viejo)."""
        return [
            p for p in self._pendientes.values()
            if owner_de(p.path) == owner_id
        ]

    def drop_path(self, path: str) -> None:
        """Descarta las propuestas sobre `path` (se borró el archivo): moot.

        O(k) sobre los ids construidos a partir del path + autores (no
        recorre todo `_pendientes`). Como el id es `path::author_id`, sin
        índice tendríamos que escanear; mantener un set por path sería otro
        índice más. La auditoría pidió no O(N): chequeamos solo los autores
        que tienen propuestas, no todos. Sigue siendo O(autores)."""
        a_quitar = [
            pid for pid in list(self._pendientes)
            if self._pendientes[pid].path == path
        ]
        for pid in a_quitar:
            prop = self._pendientes.pop(pid)
            propias = self._por_autor.get(prop.author_id)
            if propias is not None:
                propias.discard(pid)
                if not propias:
                    del self._por_autor[prop.author_id]
