"""Codec del protocolo: serializa (`encode`) y reconstruye (`decode`).

Tercera mitad del paquete `protocol` (ver `messages.py` para las FORMAS y
`validation.py` para los topes/validadores). `encode` vuelca un dataclass de
`messages.py` a JSON listo para el socket. `decode` hace el camino inverso
con validación estricta: cada campo pasa por los helpers de `validation.py`,
así que cualquier payload inválido sube como `ProtocolError`/`ValueError`
con un mensaje legible — nunca un `KeyError` crudo que tumbe la conexión.

`protocol/__init__.py` re-exporta `encode`/`decode`: el resto del backend
sigue haciendo `from ..protocol import encode, decode` sin enterarse del
corte.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from .messages import (
    AdminAssignManyMessage,
    AdminAssignMessage,
    AdminInfoMessage,
    AuthErrorMessage,
    AuthOkMessage,
    ClaimMessage,
    CloneMessage,
    CommitMessage,
    CreateInviteMessage,
    CreateTeamMessage,
    DeleteMessage,
    GitRefreshMessage,
    GitResultMessage,
    GitStatusMessage,
    ImpactMessage,
    InitMessage,
    InviteCreatedMessage,
    LeaveMessage,
    LobbyMessage,
    LoginMessage,
    Message,
    OwnershipMessage,
    PresenceMessage,
    PresenceState,
    Proposal,
    ProposalMessage,
    PushMessage,
    RedeemInviteMessage,
    RegisterMessage,
    ResolveMessage,
    SaveMessage,
    SelectTeamMessage,
    SessionMessage,
    TeamReadyMessage,
    UpdateMessage,
    WelcomeMessage,
)
from .validation import (
    MAX_FRAME_BYTES,
    ProtocolError,
    _MAX_CONTENT,
    _MAX_MESSAGE,
    _MAX_PASSWORD,
    _MAX_PATH,
    _MAX_TOKEN,
    _MAX_URL,
    _MAX_USERNAME,
    _bool,
    _dict_str,
    _int,
    _list_str,
    _str,
)


def _presence_state(d: object) -> "PresenceState":
    """Construye `PresenceState` con validación explícita por campo
    (BACKEND-AUDIT-0032: antes `PresenceState(**d)` truena con campos extra
    o tipos incorrectos)."""
    if not isinstance(d, dict):
        raise ProtocolError("presence_state debe ser objeto")
    path = d.get("path")
    if path is not None and not isinstance(path, str):
        raise ProtocolError("'path' inválido en presence_state")
    if isinstance(path, str) and len(path) > _MAX_PATH:
        raise ProtocolError("'path' excede tope en presence_state")
    return PresenceState(
        client_id=_str(d.get("client_id"), campo="client_id", max_len=_MAX_USERNAME),
        name=_str(d.get("name"), campo="name", max_len=_MAX_USERNAME),
        color=_str(d.get("color"), campo="color", max_len=32),
        path=path,
        line=_int(d.get("line"), default=1, minimo=0, maximo=10_000_000, campo="line"),
    )


def _proposal(d: object) -> "Proposal":
    if not isinstance(d, dict):
        raise ProtocolError("proposal debe ser objeto")
    return Proposal(
        id=_str(d.get("id"), campo="id", max_len=_MAX_PATH + _MAX_USERNAME + 8),
        path=_str(d.get("path"), campo="path", max_len=_MAX_PATH),
        author_id=_str(d.get("author_id"), campo="author_id", max_len=_MAX_USERNAME),
        author_name=_str(d.get("author_name"), campo="author_name", max_len=_MAX_USERNAME),
        content=_str(d.get("content"), campo="content", max_len=_MAX_CONTENT),
    )


def encode(message: Message) -> str:
    """Convierte un mensaje tipado a JSON listo para enviar por el socket.

    `asdict` viene de dataclasses y convierte la instancia a un dict recursivamente.
    El campo `type` se incluye automáticamente porque es un campo normal del
    dataclass (no un ClassVar). El receptor usará ese `type` para saber qué
    clase reconstruir.
    """
    return json.dumps(asdict(message))


def decode(raw: str | bytes) -> Message:
    """Parsea un frame WS y devuelve la instancia correcta según el `type`.

    Endurecido (BACKEND-AUDIT-0031, -0032, -0033, -0271): cualquier payload
    inválido se levanta como `ProtocolError`/`ValueError` con un mensaje legible.
    Antes un `decode({})` truena con `KeyError`; ahora con `ProtocolError("falta
    'type'")`. Sin acceso a `data["x"]` desnudo: todos los campos pasan por
    helpers que validan tipo/tope.
    """
    # Tope HARD del frame antes de parsear (BACKEND-AUDIT-0271).
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) > MAX_FRAME_BYTES:
            raise ProtocolError(
                f"frame demasiado grande ({len(raw)} > {MAX_FRAME_BYTES} bytes)"
            )
    elif isinstance(raw, str):
        if len(raw) > MAX_FRAME_BYTES:
            raise ProtocolError(
                f"frame demasiado grande ({len(raw)} > {MAX_FRAME_BYTES} bytes)"
            )
    else:
        raise ProtocolError("frame debe ser texto o bytes")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"JSON inválido: {e.msg}") from None
    if not isinstance(data, dict):
        raise ProtocolError("el mensaje debe ser un objeto JSON")
    kind = data.get("type")
    if not isinstance(kind, str):
        raise ProtocolError("falta 'type'")

    try:
        if kind == "init":
            return InitMessage(files=_dict_str(data.get("files"), campo="files"))
        if kind == "update":
            return UpdateMessage(
                path=_str(data.get("path"), max_len=_MAX_PATH, campo="path",
                          permitir_vacio=False),
                content=_str(data.get("content"), max_len=_MAX_CONTENT,
                             campo="content"),
            )
        if kind == "delete":
            return DeleteMessage(
                path=_str(data.get("path"), max_len=_MAX_PATH, campo="path",
                          permitir_vacio=False),
            )
        if kind == "save":
            return SaveMessage(
                path=_str(data.get("path"), max_len=_MAX_PATH, campo="path",
                          permitir_vacio=False),
            )
        if kind == "welcome":
            return WelcomeMessage(
                you=_presence_state(data.get("you")),
                peers=[_presence_state(p) for p in (data.get("peers") or [])],
            )
        if kind == "presence":
            # Del cliente solo exigimos `path` y `line`. Identidad la rellena
            # el server desde su registro.
            return PresenceMessage(
                client_id=_str(data.get("client_id"), max_len=_MAX_USERNAME,
                               campo="client_id"),
                name=_str(data.get("name"), max_len=_MAX_USERNAME, campo="name"),
                color=_str(data.get("color"), max_len=32, campo="color"),
                path=_str(data.get("path"), max_len=_MAX_PATH, campo="path",
                          permitir_vacio=False),
                line=_int(data.get("line"), default=1, minimo=0,
                          maximo=10_000_000, campo="line"),
            )
        if kind == "leave":
            return LeaveMessage(
                client_id=_str(data.get("client_id"), max_len=_MAX_USERNAME,
                               campo="client_id", permitir_vacio=False),
            )
        if kind == "claim":
            return ClaimMessage(
                path=_str(data.get("path"), max_len=_MAX_PATH, campo="path",
                          permitir_vacio=False),
            )
        if kind == "ownership":
            return OwnershipMessage(
                owners=_dict_str(data.get("owners"), campo="owners",
                                 max_val=_MAX_USERNAME),
            )
        if kind == "proposal":
            return ProposalMessage(proposal=_proposal(data.get("proposal")))
        if kind == "resolve":
            return ResolveMessage(
                proposal_id=_str(data.get("proposal_id"),
                                 max_len=_MAX_PATH + _MAX_USERNAME + 8,
                                 campo="proposal_id", permitir_vacio=False),
                accept=_bool(data.get("accept"), campo="accept"),
            )
        if kind == "impact":
            return ImpactMessage(
                source_path=_str(data.get("source_path"), max_len=_MAX_PATH,
                                 campo="source_path"),
                author_name=_str(data.get("author_name"), max_len=_MAX_USERNAME,
                                 campo="author_name"),
                affected_path=_str(data.get("affected_path"), max_len=_MAX_PATH,
                                   campo="affected_path"),
                symbols=_list_str(data.get("symbols"), campo="symbols"),
                motivos=_list_str(data.get("motivos"), campo="motivos"),
                cadena=_list_str(data.get("cadena"), campo="cadena"),
                severidades=_list_str(data.get("severidades"), campo="severidades"),
            )
        if kind == "register":
            return RegisterMessage(
                username=_str(data.get("username"), max_len=_MAX_USERNAME,
                              campo="username", permitir_vacio=False),
                password=_str(data.get("password"), max_len=_MAX_PASSWORD,
                              campo="password", permitir_vacio=False),
            )
        if kind == "login":
            return LoginMessage(
                username=_str(data.get("username"), max_len=_MAX_USERNAME,
                              campo="username", permitir_vacio=False),
                password=_str(data.get("password"), max_len=_MAX_PASSWORD,
                              campo="password", permitir_vacio=False),
            )
        if kind == "session":
            return SessionMessage(
                token=_str(data.get("token"), max_len=_MAX_TOKEN, campo="token",
                           permitir_vacio=False),
            )
        if kind == "auth_ok":
            return AuthOkMessage(
                username=_str(data.get("username"), max_len=_MAX_USERNAME,
                              campo="username", permitir_vacio=False),
                token=_str(data.get("token"), max_len=_MAX_TOKEN, campo="token"),
            )
        if kind == "auth_error":
            return AuthErrorMessage(
                reason=_str(data.get("reason"), max_len=_MAX_MESSAGE, campo="reason"),
            )
        if kind == "git_status":
            return GitStatusMessage(
                available=_bool(data.get("available"), campo="available"),
                branch=_str(data.get("branch"), max_len=256, campo="branch"),
                changes=_int(data.get("changes"), default=0, minimo=0,
                             maximo=10_000_000, campo="changes"),
                commits=_list_str(data.get("commits"), campo="commits"),
            )
        if kind == "git_refresh":
            return GitRefreshMessage()
        if kind == "commit":
            return CommitMessage(
                message=_str(data.get("message"), max_len=_MAX_MESSAGE,
                             campo="message", permitir_vacio=False),
            )
        if kind == "git_result":
            return GitResultMessage(
                ok=_bool(data.get("ok"), campo="ok"),
                detail=_str(data.get("detail"), max_len=_MAX_MESSAGE,
                            campo="detail"),
                pr_url=_str(data.get("pr_url"), max_len=_MAX_URL, campo="pr_url"),
            )
        if kind == "clone":
            return CloneMessage(
                url=_str(data.get("url"), max_len=_MAX_URL, campo="url",
                         permitir_vacio=False),
                username=_str(data.get("username"), max_len=_MAX_USERNAME,
                              campo="username", permitir_vacio=False),
                token=_str(data.get("token"), max_len=_MAX_TOKEN, campo="token",
                           permitir_vacio=False),
            )
        if kind == "push":
            return PushMessage(
                username=_str(data.get("username"), max_len=_MAX_USERNAME,
                              campo="username", permitir_vacio=False),
                token=_str(data.get("token"), max_len=_MAX_TOKEN, campo="token",
                           permitir_vacio=False),
                url=_str(data.get("url"), max_len=_MAX_URL, campo="url"),
                rama=_str(data.get("rama"), max_len=256, campo="rama"),
            )
        if kind == "admin_info":
            return AdminInfoMessage(
                is_admin=_bool(data.get("is_admin"), campo="is_admin"),
                users=_list_str(data.get("users"), max_items=10_000,
                                max_len=_MAX_USERNAME, campo="users"),
            )
        if kind == "admin_assign":
            return AdminAssignMessage(
                path=_str(data.get("path"), max_len=_MAX_PATH, campo="path",
                          permitir_vacio=False),
                username=_str(data.get("username"), max_len=_MAX_USERNAME,
                              campo="username"),
            )
        if kind == "admin_assign_many":
            return AdminAssignManyMessage(
                paths=_list_str(data.get("paths"), max_len=_MAX_PATH,
                                max_items=10_000, campo="paths"),
                username=_str(data.get("username"), max_len=_MAX_USERNAME,
                              campo="username"),
            )
        if kind == "lobby":
            return LobbyMessage(
                teams=list(data.get("teams") or []),
                error=_str(data.get("error"), max_len=_MAX_MESSAGE, campo="error"),
            )
        if kind == "create_team":
            return CreateTeamMessage(
                nombre=_str(data.get("nombre"), max_len=128, campo="nombre",
                            permitir_vacio=False),
            )
        if kind == "redeem_invite":
            return RedeemInviteMessage(
                code=_str(data.get("code"), max_len=256, campo="code",
                          permitir_vacio=False),
            )
        if kind == "select_team":
            return SelectTeamMessage(
                team_id=_str(data.get("team_id"), max_len=128, campo="team_id",
                             permitir_vacio=False),
            )
        if kind == "team_ready":
            return TeamReadyMessage(
                team_id=_str(data.get("team_id"), max_len=128, campo="team_id",
                             permitir_vacio=False),
                nombre=_str(data.get("nombre"), max_len=128, campo="nombre"),
                rol=_str(data.get("rol"), max_len=32, campo="rol"),
            )
        if kind == "create_invite":
            return CreateInviteMessage()
        if kind == "invite_created":
            return InviteCreatedMessage(
                code=_str(data.get("code"), max_len=256, campo="code",
                          permitir_vacio=False),
            )
    except ProtocolError:
        raise
    except (KeyError, TypeError, ValueError) as e:
        # Cualquier otra excepción se normaliza a ProtocolError con un mensaje
        # legible (BACKEND-AUDIT-0031). El server lo trata como mensaje malo
        # y NO crashea la conexión.
        raise ProtocolError(f"mensaje inválido: {e}") from None
    raise ProtocolError(f"tipo de mensaje desconocido: {kind!r}")
