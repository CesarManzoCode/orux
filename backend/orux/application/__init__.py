"""Application layer: use cases. Orquestan dominio + ports, sin conocer el
transporte (WebSocket / HTTP).

Cada use case es una función async pura que recibe:
- el `TeamRuntime` (estado vivo del equipo: workspace, ownership, proposals, roster);
- los Ports que necesita (`OwnershipStorePort`, `ProposalsStorePort`, etc.);
- un Command (dataclass con los datos de entrada);

…y devuelve un Result (dataclass con los efectos que el inbound adapter debe
publicar). El inbound (`adapters/inbound/websocket/`) traduce el Result a
mensajes del protocolo y los envía; el use case no sabe que existe un WS.

Esto separa estrictamente: protocolo (decode/encode) está en inbound;
orquestación en application; estado/reglas en domain.
"""

from .http_use_cases import (
    aplicar_evento_stripe,
    borrar_team,
    borrar_usuario,
    cambiar_plan,
    detalle_team,
    listar_teams,
    listar_usuarios,
    login_operador,
    operador_de_token,
)
from .impacto import (
    ImpactoEfectos,
    PropagarRenameEfectos,
    calcular_impacto_save,
    calcular_propagar_rename,
)
from .use_cases import (
    AdminAssignCommand,
    AdminAssignManyCommand,
    AdminAssignResult,
    ClaimCommand,
    ClaimResult,
    CloneCommand,
    CloneResult,
    CommitCommand,
    CommitResult,
    CreateInviteCommand,
    CreateInviteResult,
    DeleteCommand,
    DeleteResult,
    PresenceCommand,
    PresenceResult,
    PushCommand,
    PushResult,
    ResolveCommand,
    ResolveResult,
    UpdateCommand,
    UpdateResult,
    admin_assign_many_use_case,
    admin_assign_use_case,
    claim_use_case,
    clone_use_case,
    commit_use_case,
    create_invite_use_case,
    delete_use_case,
    presence_use_case,
    push_use_case,
    resolve_use_case,
    update_use_case,
)

__all__ = [
    "AdminAssignCommand",
    "AdminAssignManyCommand",
    "AdminAssignResult",
    "ClaimCommand",
    "ClaimResult",
    "CloneCommand",
    "CloneResult",
    "CommitCommand",
    "CommitResult",
    "CreateInviteCommand",
    "CreateInviteResult",
    "DeleteCommand",
    "DeleteResult",
    "ImpactoEfectos",
    "PresenceCommand",
    "PresenceResult",
    "PropagarRenameEfectos",
    "PushCommand",
    "PushResult",
    "ResolveCommand",
    "ResolveResult",
    "UpdateCommand",
    "UpdateResult",
    "admin_assign_many_use_case",
    "admin_assign_use_case",
    "aplicar_evento_stripe",
    "borrar_team",
    "borrar_usuario",
    "calcular_impacto_save",
    "calcular_propagar_rename",
    "cambiar_plan",
    "claim_use_case",
    "clone_use_case",
    "commit_use_case",
    "create_invite_use_case",
    "delete_use_case",
    "detalle_team",
    "listar_teams",
    "listar_usuarios",
    "login_operador",
    "operador_de_token",
    "presence_use_case",
    "push_use_case",
    "resolve_use_case",
    "update_use_case",
]
