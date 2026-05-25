"""`SemanticAnalysisAdapter`: cumple `AnalysisPort` delegando a `analysis/`.

El módulo `analysis/` está compuesto por funciones puras (impacto, motivos,
tiers.lenguaje_de, tiers.analizador_efectivo) y la clase `Rename`. El
adapter es delgado: las llama directo.

`impacto_transitivo` NO está en el Port porque requiere callbacks
inyectados de bajo nivel; el caller (`server/impacto.py`) lo usa
directamente como función pura.
"""

from __future__ import annotations

from orux.analysis import impacto as analizar_impacto
from orux.analysis import motivos as analizar_motivos
from orux.analysis import tiers
from orux.analysis.rename import (
    Rename,
    aplicar_rename as _aplicar_rename,
    detectar_rename as _detectar_rename,
    texto_sugerencia as _texto_sugerencia,
)


class SemanticAnalysisAdapter:
    def lenguaje_de(self, path: str) -> str | None:
        return tiers.lenguaje_de(path)

    def analizador_efectivo(self, path: str, sesion) -> str:
        return tiers.analizador_efectivo(path, sesion)

    def impacto(
        self,
        workspace: dict[str, str],
        path: str,
        viejo: str,
        nuevo: str,
        sesion=None,
    ) -> dict[str, list[str]]:
        return analizar_impacto(workspace, path, viejo, nuevo, sesion)

    def motivos(
        self,
        path: str,
        viejo: str,
        nuevo: str,
        sesion=None,
    ) -> dict[str, str]:
        return analizar_motivos(path, viejo, nuevo, sesion)

    def detectar_rename(
        self, path: str, viejo: str, nuevo: str,
    ) -> Rename | None:
        return _detectar_rename(path, viejo, nuevo)

    def aplicar_rename(
        self, contenido: str, viejo_nombre: str, nuevo_nombre: str,
    ) -> str:
        return _aplicar_rename(contenido, viejo_nombre, nuevo_nombre)

    def texto_sugerencia(self, r: Rename) -> str:
        return _texto_sugerencia(r)
