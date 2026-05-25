"""Ports de persistencia — contratos formales que el dominio exige.

Cada Port es un `typing.Protocol` (`runtime_checkable`): una implementación es
válida si tiene los métodos con las firmas correctas, sin herencia, sin
registro manual. Implementaciones vivas (ver módulo correspondiente):

| Port                    | Dev / tests                | Producción           |
| ----------------------- | -------------------------- | -------------------- |
| WorkspaceStoragePort    | DiskStorage (tmp)          | DiskStorage          |
| OwnershipStorePort      | JsonOwnershipStore         | PgOwnershipStore     |
| ProposalsStorePort      | MemProposalsStore          | PgProposalsStore     |
| UserStorePort           | JsonUserStore              | PgUserStore          |
| WebhooksStorePort       | (no aplica)                | PgWebhooksStore      |
| TeamStorePort           | MemTeamStore               | PgTeamStore          |

# Diseño sync vs async

La mayoría de Ports son ASYNC: el server es asyncio, Postgres es async nativo
(asyncpg), y los stores en memoria devuelven al instante. Async unifica la
superficie y elimina el bridging sync/async en el dispatch.

`WorkspaceStoragePort` es SYNC a propósito: el hot path (broadcast tras
update) NO debe pagar el costo de un await por cada tecla. El IO real es
trivial (1 archivo de texto por update) y queda atrapado y logueado en
`Workspace.update` para no tumbar el tiempo real si falla.

# Flujo write-through

El dominio (`state.Ownership`, `state.Proposals`) es PURO MEMORIA SYNC. El
caller (TeamRuntime / SyncServer dispatch) muta el dominio y después hace
`await store.guardar(...)`. Si el guardar falla, el caller decide rollback
de la mutación en memoria. Esto reemplaza el modelo viejo donde el dominio
hacía persistencia inline (JSON) y el rollback estaba enredado con la
mutación: ahora el dominio es testeable sin tocar disco y el caller es el
único que sabe de la asimetría memoria/persistencia.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..protocol import Proposal


@runtime_checkable
class WorkspaceStoragePort(Protocol):
    """Persistencia del workspace (archivos del equipo) en disco.

    SYNC a propósito: el hot path no espera IO. Implementación canónica:
    `state.DiskStorage`.
    """

    def guardar(self, path: str, content: str) -> None: ...

    def borrar(self, path: str) -> None: ...

    def cargar(self) -> dict[str, str]: ...


@runtime_checkable
class OwnershipStorePort(Protocol):
    """Persistencia del mapa ownership de UN equipo.

    El dominio (`state.Ownership`) es la verdad en memoria; este Port
    escribe-a-través: `cargar` al abrir el equipo, `guardar` tras cada
    mutación (claim / asignar / liberar / purgar_usuario / reset).
    Implementaciones: `adapters.json.ownership.JsonOwnershipStore` (modo
    dev, archivo local) y `db.stores.PgOwnershipStore` (producción).
    """

    async def cargar(self, team_id: str) -> dict[str, str]: ...

    async def guardar(self, team_id: str, owners: dict[str, str]) -> None: ...


@runtime_checkable
class ProposalsStorePort(Protocol):
    """Persistencia de propuestas tentativas por equipo.

    El hot path sigue siendo el dict en memoria de `state.Proposals`; este
    Port se carga al abrir el equipo y se escribe-a-través tras cada
    mutación (put / pop / drop_path / borrar_todo).
    """

    async def cargar(self, team_id: str) -> list[Proposal]: ...

    async def guardar(self, team_id: str, prop: Proposal) -> None: ...

    async def borrar(self, team_id: str, proposal_id: str) -> None: ...

    async def borrar_path(self, team_id: str, path: str) -> None: ...

    async def borrar_todo(self, team_id: str) -> None: ...


@runtime_checkable
class UserStorePort(Protocol):
    """Persistencia de usuarios (identidad).

    Async por consistencia con el resto de la persistencia: `PgUserStore` es
    async nativo y `JsonUserStore` envuelve la IO en `to_thread` para que el
    caller vea una sola superficie.
    """

    async def existe(self, username: str) -> bool: ...

    async def usuarios(self) -> list[str]: ...

    async def registrar(self, username: str, password: str) -> str: ...

    async def verificar(self, username: str, password: str) -> bool: ...

    async def asegurar_externo(self, username: str) -> str: ...

    async def epoch(self, username: str) -> int: ...

    async def revocar_sesiones(self, username: str) -> None: ...

    async def borrar(self, username: str) -> bool: ...


@runtime_checkable
class WebhooksStorePort(Protocol):
    """Idempotencia de webhooks de Stripe por event_id.

    Implementación canónica: `db.stores.PgWebhooksStore`. No hay versión JSON
    (el modo dev no procesa webhooks reales).
    """

    async def marcar(self, event_id: str) -> bool: ...

    async def purgar(self, antes_de_segundos: int = ...) -> int: ...


@runtime_checkable
class TeamStorePort(Protocol):
    """Persistencia del dominio equipos / membresía / invitaciones.

    Implementaciones: `teams.store.MemTeamStore` (dev/tests) y
    `teams.pg.PgTeamStore` (producción). Ya isomorfas en superficie; este
    Port lo declara formal.
    """

    # --- Equipos ---
    async def crear_equipo(self, nombre: str, creador: str) -> dict: ...

    async def equipo(self, team_id: str) -> dict | None: ...

    async def plan(self, team_id: str) -> str: ...

    async def set_plan(self, team_id: str, plan: str) -> None: ...

    async def actualizar_suscripcion(
        self, team_id: str, plan: str, subscription_id: str,
    ) -> None: ...

    async def suscripcion(self, team_id: str) -> str: ...

    async def contar_miembros(self, team_id: str) -> int: ...

    async def todos(self) -> list[dict]: ...

    async def equipos_de(self, usuario: str) -> list[dict]: ...

    async def borrar(self, team_id: str) -> bool: ...

    # --- Membresía ---
    async def es_miembro(self, team_id: str, usuario: str) -> bool: ...

    async def rol(self, team_id: str, usuario: str) -> str | None: ...

    async def miembros(self, team_id: str) -> list[dict]: ...

    # --- Invitaciones ---
    async def crear_invitacion(
        self, team_id: str, por_usuario: str,
    ) -> str: ...

    async def redimir(
        self, code: str, usuario: str,
    ) -> dict | None: ...
