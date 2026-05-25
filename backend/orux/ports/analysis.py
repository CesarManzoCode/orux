"""Ports del análisis semántico: impacto + rename + factory de sesiones LSP.

# Diseño

El análisis tiene tres caras públicas que el server usa:

1. **`AnalysisPort`** — el motor de impacto/rename. `impacto`/`motivos`/
   `impacto_transitivo` calculan a quién le importa un cambio;
   `detectar_rename`/`aplicar_rename`/`texto_sugerencia` cubren el codemod.
2. **`LspFactoryPort`** — arranca una sesión LSP por lenguaje
   (lazy: subprocess pyright/tsserver/etc). El runtime cachea la sesión
   tibia y la pasa al AnalysisPort en cada análisis.
3. **`LspSession`** — protocolo mínimo de la sesión LSP que el runtime
   ciclo de vida (`disponible`/`cerrar`). El análisis recibe la sesión
   como `object | None` porque sólo la pasa, no la inspecciona — la
   inspección vive dentro del adapter del Port.

Implementación canónica: `adapters.analysis.semantic.SemanticAnalysisAdapter`
(envuelve `analysis.impacto`/`motivos`/`tiers`/`rename`/`transitive`) +
`adapters.analysis.lsp_factory.LspFactoryAdapter` (envuelve `arrancar_lsp`).

Como con los demás Ports puros, los adapters son delgados — encapsulan el
cableado, no reimplementan la lógica.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..analysis.rename import Rename


@runtime_checkable
class LspSession(Protocol):
    """Sesión LSP viva. El runtime sólo necesita estos dos métodos para el
    ciclo de vida (chequeo de salud + cierre); el resto del comportamiento
    lo consume el AnalysisPort internamente."""

    def disponible(self) -> bool: ...

    def cerrar(self) -> None: ...


@runtime_checkable
class LspFactoryPort(Protocol):
    """Crea sesiones LSP por lenguaje. None si no se pudo arrancar
    (lenguaje sin server, binario no instalado, OOM, lo que sea); el caller
    degrada al siguiente tier sin romper."""

    def arrancar(self, lang: str, ws_dir: str) -> LspSession | None: ...


@runtime_checkable
class AnalysisPort(Protocol):
    """Análisis semántico de impacto y rename de un cambio de archivo.

    Implementación canónica: `adapters.analysis.semantic.SemanticAnalysisAdapter`.
    El `sesion` se pasa opaco: el adapter lo inspecciona internamente
    (degrada solo si está caída o cooldown).
    """

    def lenguaje_de(self, path: str) -> str | None: ...

    def analizador_efectivo(
        self, path: str, sesion: LspSession | None,
    ) -> str: ...

    def impacto(
        self,
        workspace: dict[str, str],
        path: str,
        viejo: str,
        nuevo: str,
        sesion: LspSession | None = None,
    ) -> dict[str, list[str]]: ...

    def motivos(
        self,
        path: str,
        viejo: str,
        nuevo: str,
        sesion: LspSession | None = None,
    ) -> dict[str, str]: ...

    def detectar_rename(
        self, path: str, viejo: str, nuevo: str,
    ) -> Rename | None: ...

    def aplicar_rename(
        self, contenido: str, viejo_nombre: str, nuevo_nombre: str,
    ) -> str: ...

    def texto_sugerencia(self, r: Rename) -> str: ...
