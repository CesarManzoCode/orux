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

from .document import Document


class Workspace:
    def __init__(self) -> None:
        # Diccionario interno: path (string) -> Document. Es la fuente de verdad
        # del servidor sobre qué archivos existen y qué contienen.
        self._documents: dict[str, Document] = {}

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
        """
        self.get_or_create(path).update(content)
