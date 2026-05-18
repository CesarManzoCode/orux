"""Documento individual: la unidad mínima de contenido editable.

En esta fase un Document es solo un wrapper alrededor de un string. Parece trivial
y lo es a propósito. La razón de envolverlo en una clase en vez de usar el string
crudo es que más adelante este lugar va a crecer:

- Cuando metamos CRDT, el contenido dejará de ser un string plano y será un
  estructura tipo Y.Text que aplica operaciones en vez de sobrescrituras.
- Cuando metamos historia, este Document recordará versiones anteriores.
- Cuando metamos ownership por sección, el Document sabrá qué rangos le
  pertenecen a quién.

Hoy mantener todo eso simple — un string envuelto — significa que el resto del
sistema (servidor, workspace, protocolo) ya habla con un objeto Document, y
cuando llegue el momento, los cambios viven dentro de esta clase sin afectar
nada de afuera.
"""

from __future__ import annotations


class Document:
    def __init__(self, content: str = "") -> None:
        self._content = content

    @property
    def content(self) -> str:
        return self._content

    def update(self, new_content: str) -> None:
        # En la capa cero, "update" es "reemplaza todo". Last-write-wins.
        # En la capa que meta CRDT, esto se reemplaza por aplicar una operación
        # (insertar en posición N, borrar rango M..N), no por sobrescribir.
        self._content = new_content
