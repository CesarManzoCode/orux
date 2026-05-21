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
        if not isinstance(content, str):
            raise TypeError("Document.content debe ser str")
        self._content = content

    @property
    def content(self) -> str:
        return self._content

    def update(self, new_content: str) -> str:
        """Reemplaza el contenido del documento; devuelve el VIEJO (BACKEND-AUDIT-0087).

        Devolver el viejo desacopla al caller de tener que leer-y-luego-update:
        algunos sitios (capa 5 / diff de líneas) necesitan el contenido previo
        ANTES de mutar; sin esto, llamar al revés perdía el viejo. La firma se
        mantiene útil para callers que ignoran el retorno.

        En la capa cero, "update" es "reemplaza todo". Last-write-wins.
        En la capa que meta CRDT, esto se reemplaza por aplicar una operación
        (insertar en posición N, borrar rango M..N), no por sobrescribir.
        """
        if not isinstance(new_content, str):
            raise TypeError("Document.update espera str")
        viejo = self._content
        self._content = new_content
        return viejo

    def __repr__(self) -> str:  # pragma: no cover
        return f"Document(len={len(self._content)})"
