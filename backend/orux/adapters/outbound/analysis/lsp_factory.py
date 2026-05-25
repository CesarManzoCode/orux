"""`LspFactoryAdapter`: cumple `LspFactoryPort` delegando a `arrancar_lsp`.

Pieza opcional: si en el futuro hay otra forma de obtener un Tier 0
(language servers embebidos, servicios externos), sería otro adapter.
"""

from __future__ import annotations

from orux.analysis.lsp import arrancar_lsp


class LspFactoryAdapter:
    def arrancar(self, lang: str, ws_dir: str):
        return arrancar_lsp(lang, ws_dir)
