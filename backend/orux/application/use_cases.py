"""Use cases del dominio de sesión de equipo.

Cada función es PURA respecto al transporte: recibe estado (`TeamRuntime`),
Ports y un Command; devuelve un Result que describe los efectos a publicar.
El inbound adapter del WebSocket traduce el Result a mensajes del protocolo.

# Patrón Result

Los Result usan campos opcionales (`Optional[...]`) que el inbound revisa:
si está presente, lo emite; si no, no hace nada. Esto evita una jerarquía
de eventos heredados y deja el contrato declarativo y reviewable.

# Lo que NO hacen los use cases

- No saben de WebSocket ni de `encode`/`decode`.
- No llaman a `server._broadcast*`/`_enviar_a` (eso es del transporte).
- No conocen los IDs de cliente más allá de los strings que reciben en
  el Command.

# Lo que SÍ hacen

- Mutan `rt.workspace` / `rt.ownership` / `rt.proposals` / `rt.roster`
  (estado del dominio).
- Llaman a los Ports inyectados (`ownership_store.guardar`, etc.) para
  persistencia.
- Devuelven el snapshot resultante para que el inbound lo publique.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..identity import normalizar
from ..ports import (
    GitPort,
    OwnershipStorePort,
    ProposalsStorePort,
    TeamStorePort,
)
from ..protocol import Proposal
from ..state import lineas_tocadas, path_seguro

if TYPE_CHECKING:
    from ..server.runtime import TeamRuntime


# === Update ===============================================================

@dataclass
class UpdateCommand:
    path: str
    content: str
    autor_id: str
    autor_nombre: str


@dataclass
class UpdateResult:
    # Si está, el inbound responde SÓLO al autor con el contenido viejo
    # (rechazo por colisión de línea).
    rebotar_a_autor: str | None = None
    # Si está, el inbound difunde una propuesta tentativa al dueño actual.
    propuesta_para_dueno: tuple[str, Proposal] | None = None
    # Si está, el inbound difunde el update a TODOS menos el autor.
    broadcast_update: tuple[str, str] | None = None  # (path, content)
    # Si está, el inbound difunde el ownership actualizado a todos.
    broadcast_ownership: dict[str, str] | None = None


async def update_use_case(
    rt: "TeamRuntime",
    ownership_store: OwnershipStorePort | None,
    proposals_store: ProposalsStorePort | None,
    cmd: UpdateCommand,
) -> UpdateResult:
    """Aplica un Update: con dueño ajeno -> propuesta; sin dueño y línea
    ocupada -> rebota; resto -> aplica + difunde + claim si es nuevo."""
    res = UpdateResult()
    dueño = rt.ownership.owner(cmd.path)
    if dueño is not None and dueño != cmd.autor_id:
        prop = rt.proposals.put(
            path=cmd.path,
            author_id=cmd.autor_id,
            author_name=cmd.autor_nombre,
            content=cmd.content,
        )
        if proposals_store is not None:
            await proposals_store.guardar(rt.team_id, prop)
        res.propuesta_para_dueno = (dueño, prop)
        return res

    viejo = rt.workspace.snapshot().get(cmd.path, "")
    if dueño is None:
        tocadas = lineas_tocadas(viejo, cmd.content)
        ocupadas = rt.roster.lineas_ocupadas(cmd.path, excepto=cmd.autor_id)
        if tocadas & ocupadas:
            res.rebotar_a_autor = viejo
            return res

    es_nuevo = not rt.workspace.exists(cmd.path)
    # Siembra baseline del checkpoint la 1ª vez (capa 19).
    rt._analizado.setdefault(cmd.path, viejo)
    rt.workspace.update(cmd.path, cmd.content)
    res.broadcast_update = (cmd.path, cmd.content)
    if es_nuevo and dueño is None:
        rt.ownership.claim(cmd.path, cmd.autor_id)
        if ownership_store is not None:
            await ownership_store.guardar(rt.team_id, rt.ownership.snapshot())
        res.broadcast_ownership = rt.ownership.snapshot()
    return res


# === Claim ================================================================

@dataclass
class ClaimCommand:
    path: str
    autor_id: str


@dataclass
class ClaimResult:
    broadcast_ownership: dict[str, str]


async def claim_use_case(
    rt: "TeamRuntime",
    ownership_store: OwnershipStorePort | None,
    cmd: ClaimCommand,
) -> ClaimResult:
    rt.ownership.claim(cmd.path, cmd.autor_id)
    if ownership_store is not None:
        await ownership_store.guardar(rt.team_id, rt.ownership.snapshot())
    return ClaimResult(broadcast_ownership=rt.ownership.snapshot())


# === Delete ===============================================================

@dataclass
class DeleteCommand:
    path: str
    autor_id: str


@dataclass
class DeleteResult:
    # None si el borrado no aplicó (path inexistente o dueño ajeno).
    broadcast_delete: str | None = None
    broadcast_ownership: dict[str, str] | None = None


async def delete_use_case(
    rt: "TeamRuntime",
    ownership_store: OwnershipStorePort | None,
    proposals_store: ProposalsStorePort | None,
    cmd: DeleteCommand,
) -> DeleteResult:
    res = DeleteResult()
    dueño = rt.ownership.owner(cmd.path)
    if dueño is not None and dueño != cmd.autor_id:
        return res
    if not rt.workspace.delete(cmd.path):
        return res
    rt.proposals.drop_path(cmd.path)
    if proposals_store is not None:
        await proposals_store.borrar_path(rt.team_id, cmd.path)
    rt._analizado.pop(cmd.path, None)
    cambio_owner = rt.ownership.liberar(cmd.path)
    if cambio_owner and ownership_store is not None:
        await ownership_store.guardar(rt.team_id, rt.ownership.snapshot())
    res.broadcast_delete = cmd.path
    if cambio_owner:
        res.broadcast_ownership = rt.ownership.snapshot()
    return res


# === Resolve (aprobar/rechazar propuesta) =================================

@dataclass
class ResolveCommand:
    proposal_id: str
    autor_id: str
    accept: bool


@dataclass
class ResolveResult:
    # Si se aprobó: workspace actualizado + necesita notificar impacto.
    aplicado_update: tuple[str, str, str, str] | None = None
    # ^ (path, viejo, nuevo, prop_author_id) — el inbound dispara impacto.
    nombre_autor_propuesta: str = ""
    # Si se rechazó: devolvemos al autor de la propuesta el contenido actual.
    devolver_a_autor: tuple[str, str, str] | None = None
    # ^ (author_id, path, contenido_actual)


async def resolve_use_case(
    rt: "TeamRuntime",
    proposals_store: ProposalsStorePort | None,
    cmd: ResolveCommand,
) -> ResolveResult:
    res = ResolveResult()
    prop = rt.proposals.get(cmd.proposal_id)
    if prop is None or rt.ownership.owner(prop.path) != cmd.autor_id:
        return res  # carrera benigna
    rt.proposals.pop(cmd.proposal_id)
    if proposals_store is not None:
        await proposals_store.borrar(rt.team_id, cmd.proposal_id)
    if cmd.accept:
        viejo = rt.workspace.snapshot().get(prop.path, "")
        rt.workspace.update(prop.path, prop.content)
        res.aplicado_update = (
            prop.path, viejo, prop.content, prop.author_id,
        )
        res.nombre_autor_propuesta = prop.author_name
    else:
        res.devolver_a_autor = (
            prop.author_id,
            prop.path,
            rt.workspace.snapshot().get(prop.path, ""),
        )
    return res


# === AdminAssign ==========================================================

@dataclass
class AdminAssignCommand:
    path: str
    username: str
    autor_id: str


@dataclass
class AdminAssignResult:
    broadcast_ownership: dict[str, str] | None = None


async def admin_assign_use_case(
    rt: "TeamRuntime",
    ownership_store: OwnershipStorePort | None,
    teams: TeamStorePort,
    cmd: AdminAssignCommand,
) -> AdminAssignResult:
    """NOTA: la compuerta de admin del equipo se chequea EN EL INBOUND
    (necesita logging contextual con el detalle de la operación). Este
    use case asume que ya pasó."""
    res = AdminAssignResult()
    aplicado = False
    if cmd.username:
        destino = normalizar(cmd.username)
        if await teams.es_miembro(rt.team_id, destino):
            rt.ownership.asignar(cmd.path, destino)
            aplicado = True
    else:
        aplicado = rt.ownership.liberar(cmd.path)
    if aplicado:
        if ownership_store is not None:
            await ownership_store.guardar(rt.team_id, rt.ownership.snapshot())
        res.broadcast_ownership = rt.ownership.snapshot()
    return res


# === AdminAssignMany ======================================================

@dataclass
class AdminAssignManyCommand:
    paths: list[str]
    username: str
    autor_id: str


async def admin_assign_many_use_case(
    rt: "TeamRuntime",
    ownership_store: OwnershipStorePort | None,
    teams: TeamStorePort,
    cmd: AdminAssignManyCommand,
) -> AdminAssignResult:
    res = AdminAssignResult()
    destino = normalizar(cmd.username) if cmd.username else ""
    if destino and not await teams.es_miembro(rt.team_id, destino):
        return res  # destino no es miembro → no-op
    aplicado = False
    for p in cmd.paths:
        if not path_seguro(p):
            continue
        if destino:
            rt.ownership.asignar(p, destino)
            aplicado = True
        elif rt.ownership.liberar(p):
            aplicado = True
    if aplicado:
        if ownership_store is not None:
            await ownership_store.guardar(rt.team_id, rt.ownership.snapshot())
        res.broadcast_ownership = rt.ownership.snapshot()
    return res


# === CreateInvite =========================================================

@dataclass
class CreateInviteCommand:
    autor_id: str


@dataclass
class CreateInviteResult:
    # None si falló (carrera benigna: dejó de ser admin, etc.).
    code: str | None = None


async def create_invite_use_case(
    rt: "TeamRuntime",
    teams: TeamStorePort,
    cmd: CreateInviteCommand,
) -> CreateInviteResult:
    """Compuerta de admin chequeada en el inbound."""
    from ..teams import TeamError  # evitar import circular
    try:
        code = await teams.crear_invitacion(rt.team_id, cmd.autor_id)
        return CreateInviteResult(code=code)
    except TeamError:
        return CreateInviteResult()


# === Presence =============================================================

@dataclass
class PresenceCommand:
    autor_id: str
    path: str
    line: int


@dataclass
class PresenceResult:
    # None si la presencia no cambió (no broadcast).
    broadcast_presence: tuple[str, str, str, str, int] | None = None
    # ^ (client_id, name, color, path, line)


async def presence_use_case(
    rt: "TeamRuntime",
    cmd: PresenceCommand,
) -> PresenceResult:
    estado = rt.roster.mover(cmd.autor_id, cmd.path, cmd.line)
    if estado is None:
        return PresenceResult()
    return PresenceResult(
        broadcast_presence=(
            estado.client_id,
            estado.name,
            estado.color,
            estado.path,
            estado.line,
        ),
    )


# === Git: Commit / Clone / Push ==========================================
#
# Los git use cases SÓLO contienen la lógica que es independiente del
# transporte: armar el autor, llamar al GitPort en el thread correcto, mapear
# el resultado. Los locks (`rt._git_lock`, `rt._estado_lock`) los maneja el
# inbound porque son específicos de la coreografía del WS dispatch
# (intercalación con otros handlers del mismo runtime).


@dataclass
class CommitCommand:
    mensaje: str
    autor_nombre: str
    autor_email: str


@dataclass
class CommitResult:
    ok: bool
    detalle: str
    # True ⇒ el inbound difunde el git status actualizado a todos.
    git_status_cambio: bool = False


async def commit_use_case(
    rt: "TeamRuntime",
    cmd: CommitCommand,
) -> CommitResult:
    if rt.git is None:
        return CommitResult(False, "git no disponible")
    msg = (cmd.mensaje or "").strip()[:500]
    if not msg:
        return CommitResult(False, "escribí un mensaje de commit")
    ok, detalle = await asyncio.to_thread(
        rt.git.commitear, msg, cmd.autor_nombre, cmd.autor_email,
    )
    return CommitResult(ok=ok, detalle=detalle, git_status_cambio=ok)


@dataclass
class CloneCommand:
    url: str
    usuario: str
    token: str
    autor_id: str


@dataclass
class CloneResult:
    ok: bool
    detalle: str
    # True ⇒ el inbound debe reiniciar el equipo (workspace cambió).
    reiniciar_equipo: bool = False


async def clone_use_case(
    rt: "TeamRuntime",
    cmd: CloneCommand,
) -> CloneResult:
    if rt.git is None:
        return CloneResult(False, "git no disponible")
    ok, detalle = await asyncio.to_thread(
        rt.git.clonar, cmd.url, cmd.usuario, cmd.token,
    )
    return CloneResult(ok=ok, detalle=detalle, reiniciar_equipo=ok)


@dataclass
class PushCommand:
    url: str
    usuario: str
    token: str
    rama: str
    autor_id: str


@dataclass
class PushResult:
    ok: bool
    detalle: str
    pr_url: str = ""
    git_status_cambio: bool = False


async def push_use_case(
    rt: "TeamRuntime",
    cmd: PushCommand,
) -> PushResult:
    if rt.git is None:
        return PushResult(False, "git no disponible")
    rama_eq = f"orux/{rt.team_id}"
    destino = (cmd.rama or "").strip() or rama_eq
    if destino == rama_eq:
        ok, detalle, pr_url = await asyncio.to_thread(
            rt.git.push_a_rama,
            cmd.usuario, cmd.token, rama_eq, cmd.url or None,
        )
    else:
        ok, detalle = await asyncio.to_thread(
            rt.git.push,
            cmd.usuario, cmd.token, cmd.url or None, destino,
        )
        pr_url = ""
    return PushResult(
        ok=ok, detalle=detalle, pr_url=pr_url, git_status_cambio=ok,
    )
