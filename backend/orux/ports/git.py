"""GitPort: contrato del adapter de git para un workspace de equipo.

Sync a propósito: las operaciones git son subprocess (commit/clone/push) y
ya están envueltas con `to_thread` por el caller (sync.py hace
`asyncio.to_thread` para no bloquear el loop). Hacer el Port async forzaría
a `to_thread` adentro del adapter mismo, lo que es asimétrico con la
realidad: la decisión de "en qué thread se corre" la toma el caller.

Implementación canónica: `git.repo.GitRepo` (próximamente movida a
`adapters/git/binary.py` como `GitBinaryAdapter` con alias para retrocompat).

`EstadoGit` vive acá porque es un value object del contrato: lo devuelve el
Port, lo consume el dominio. Sin él, el dominio importaría del adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class EstadoGit:
    """Foto de solo lectura del repo. `disponible=False` si git no se pudo usar."""

    disponible: bool
    rama: str = ""
    cambios: int = 0  # archivos sin commitear (incluye sin trackear)
    commits: list[str] = field(default_factory=list)  # últimos, "hash msg"


@runtime_checkable
class GitPort(Protocol):
    """Operaciones git sobre el workspace de UN equipo.

    Las credenciales son SIEMPRE efímeras: las pasa el caller en cada
    operación remota, el adapter no las persiste. La identidad del autor
    para `commitear` viene del usuario autenticado (capa 7), nunca del
    cliente.
    """

    def asegurar(self) -> None: ...

    def estado(self) -> EstadoGit: ...

    def commitear(
        self,
        mensaje: str,
        autor_nombre: str,
        autor_email: str,
    ) -> tuple[bool, str]: ...

    def clonar(
        self,
        url: str,
        usuario: str,
        token: str,
    ) -> tuple[bool, str]: ...

    def push(
        self,
        usuario: str,
        token: str,
        url: str | None = None,
        rama: str | None = None,
    ) -> tuple[bool, str]: ...

    def push_a_rama(
        self,
        usuario: str,
        token: str,
        rama: str,
        url: str | None = None,
    ) -> tuple[bool, str, str]: ...
