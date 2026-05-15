"""Workspace: el conjunto de archivos que el equipo está editando.

Antes (capa cero) teníamos un solo `Document` en el servidor. Ahora tenemos un
**workspace**, que es un mapa de `path -> Document`. Cada archivo vive como un
Document independiente, lo cual es importante: significa que cuando llegue el
momento de ediciones concurrentes con CRDT, cada archivo es su propio "espacio"
de sincronización y los cambios en `main.py` no compiten con cambios en `auth.py`.

Esa decisión se siente trivial ahora pero es load-bearing: toda la arquitectura
posterior (ownership por archivo, presencia por archivo, análisis semántico que
detecta usos cruzados entre archivos) asume que el archivo es la unidad mínima
de coordinación.
"""

from __future__ import annotations

import logging

from .document import Document
from .storage import DiskStorage

logger = logging.getLogger(__name__)


class Workspace:
    def __init__(self, storage: DiskStorage | None = None) -> None:
        # Diccionario interno: path (string) -> Document. Es la fuente de verdad
        # del servidor sobre qué archivos existen y qué contienen.
        self._documents: dict[str, Document] = {}
        # Persistencia opcional (capa 3). Si es None, el workspace es puramente
        # en memoria — exactamente el comportamiento de capas 1 y 2, y lo que
        # usan los tests para arrancar siempre desde cero. Si hay storage, cada
        # update se escribe a disco y el estado sobrevive a reiniciar el server.
        # La memoria sigue siendo la fuente de verdad en caliente; el disco es
        # su respaldo, no un intermediario en el hot path de retransmisión.
        self._storage = storage

    def snapshot(self) -> dict[str, str]:
        """Foto del workspace completo: path -> contenido.

        Esto es lo que el servidor manda en el InitMessage a un cliente que
        acaba de conectarse. La copia es plana (no expone los objetos Document
        internos) porque el cliente no necesita saber sobre Document — solo
        necesita el texto.
        """
        return {path: doc.content for path, doc in self._documents.items()}

    def get_or_create(self, path: str) -> Document:
        """Devuelve el Document de un path, creándolo vacío si no existe.

        Esta es la pieza que implementa "los archivos se crean al primer update".
        Decisión a futuro: si quieres que crear archivo sea explícito (botón
        "+ nuevo"), el cliente igualmente puede mandar un UpdateMessage con
        contenido vacío y este método lo crea sin distinción. Sirve para ambos
        casos sin lógica extra.
        """
        if path not in self._documents:
            self._documents[path] = Document()
        return self._documents[path]

    def update(self, path: str, content: str) -> None:
        """Aplica un cambio: 'el archivo en `path` ahora contiene `content`'.

        Crea el archivo si no existía. Cuando llegue el CRDT real, este método
        es donde la operación se aplicará al estado del archivo (no como
        sobrescritura completa sino como una operación incremental).

        Orden importante: PRIMERO memoria, DESPUÉS disco. Si persistir falla
        (path inseguro mandado por un cliente, disco lleno, permisos), la
        memoria ya quedó coherente y la retransmisión a los demás clientes
        sigue funcionando. Persistir nunca debe poder tumbar el tiempo real:
        por eso atrapamos y logueamos en vez de propagar.
        """
        self.get_or_create(path).update(content)
        if self._storage is not None:
            try:
                self._storage.guardar(path, content)
            except Exception:
                logger.exception("no se pudo persistir %r (sigo en memoria)", path)

    def cargar_de_disco(self) -> None:
        """Reconstruye el workspace desde el storage. Se llama una vez, al arrancar.

        No re-persiste lo que lee (sería redundante: ya está en disco). Sin
        storage configurado no hace nada, así un `Workspace()` en memoria
        —el de los tests— se comporta igual que siempre.
        """
        if self._storage is None:
            return
        for path, content in self._storage.cargar().items():
            self._documents[path] = Document(content)
