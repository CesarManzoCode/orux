"""Modelo de estado del documento compartido.

Capa cero: un único documento global como string. Cuando llegue la capa 1
(múltiples archivos), este módulo es donde crece el modelo a un árbol.
"""

from __future__ import annotations


class Document:
    def __init__(self, content: str = "") -> None:
        self._content = content

    @property
    def content(self) -> str:
        return self._content

    def update(self, new_content: str) -> None:
        self._content = new_content
