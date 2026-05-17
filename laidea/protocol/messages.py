"""Tipos de mensajes que viajan por el WebSocket entre cliente y servidor.

El protocolo es el "contrato" entre las dos puntas del sistema. Tanto el servidor
como el cliente tienen que estar de acuerdo en qué mensajes se mandan y qué forma
tienen. Por eso vive en su propio módulo: si un día cambiamos cómo se envía un
update, este es el único archivo que el servidor y el cliente tienen que coordinar.

Capa 1: el documento dejó de ser un solo string y pasó a ser un mapa de
`path -> contenido`. Cada mensaje de update ahora dice a qué archivo se refiere.

Capa 2 (esta): presencia. Tres mensajes nuevos para que cada quien vea dónde
están trabajando los demás:

- `WelcomeMessage`: el servidor te lo manda al conectar. Te dice quién eres
  (identidad anónima que el servidor te asignó: id, nombre, color) y quiénes
  más están presentes ahora mismo y en qué archivo/línea (el `peers`).
- `PresenceMessage`: "estoy en este archivo, en esta línea". Es simétrico como
  `UpdateMessage`: el cliente lo manda al moverse, el servidor lo retransmite a
  los demás. El cliente solo manda `path` y `line`; el servidor rellena la
  identidad desde su registro (el cliente no puede mentir sobre quién es).
- `LeaveMessage`: el servidor lo manda a los demás cuando alguien se desconecta,
  para que su marcador desaparezca de la UI.

Decisión deliberada: la presencia es por archivo + número de línea, no posición
exacta de cursor. La línea es lo que de verdad responde "¿alguien ya está
tocando esto?" sin la fragilidad de superponer carets sobre un <textarea>.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal, Union


@dataclass(frozen=True)
class InitMessage:
    """Lo primero que el servidor manda a un cliente recién conectado.

    Lleva el snapshot completo del workspace: todos los archivos con su contenido.
    Así un cliente que llega tarde se pone al día instantáneamente sin tener que
    pedir nada extra. El campo `files` es un dict `path -> contenido`.

    Cuando agreguemos persistencia, este snapshot se construirá leyendo de disco
    en vez de leerse de memoria, pero la forma del mensaje no cambiará.
    """

    files: dict[str, str] = field(default_factory=dict)
    type: Literal["init"] = "init"


@dataclass(frozen=True)
class UpdateMessage:
    """Cambio en un archivo específico.

    Lo manda el cliente cuando edita, y lo manda el servidor cuando retransmite
    ese cambio a los demás clientes conectados. La misma forma sirve para ambos
    sentidos, lo cual mantiene el protocolo simétrico y simple.

    El `path` identifica el archivo. Si el archivo no existe todavía en el
    servidor, el update lo crea — así no necesitamos un mensaje aparte de
    "crear archivo". Cuando llegue la capa de borrado, sí necesitaremos un
    mensaje nuevo (DeleteMessage), porque "borrar" no se puede colar dentro de
    un "update".
    """

    path: str
    content: str
    type: Literal["update"] = "update"


@dataclass(frozen=True)
class DeleteMessage:
    """Borrar un archivo. Simétrico: el cliente lo pide, el servidor lo confirma.

    Lo que un update no podía colar (decía el comentario de arriba): borrar es
    una operación distinta de editar, necesita su propio mensaje. Reglas de
    coordinación (capa 4): solo borra quien puede — el dueño, o cualquiera si
    el archivo no tiene dueño. El servidor lo difunde a TODOS (incluido quien
    lo pidió) para que el estado converja sin que nadie adivine.
    """

    path: str
    type: Literal["delete"] = "delete"


@dataclass(frozen=True)
class SaveMessage:
    """Capa 19: checkpoint explícito de un archivo (el Ctrl+S del dev).

    El contenido ya viaja en vivo por `update` (presencia/locks/sync no
    cambian). Esto NO guarda nada —no hay estado sin guardar— : es la señal
    de "considero este punto coherente, analizá el impacto AHORA". El
    análisis dejó de correr por tecla (ruido, falsos avisos sobre código a
    medio escribir, tormenta de queries LSP) y corre solo acá: el autor
    decide cuándo se publican las consecuencias de su cambio. Solo
    cliente->servidor; el server no lo retransmite (no es estado a converger,
    es un disparador).
    """

    path: str
    type: Literal["save"] = "save"


@dataclass(frozen=True)
class PresenceState:
    """Dónde está trabajando un cliente. Es el "estado de presencia" de una persona.

    No es un mensaje que viaja solo: viaja embebido dentro de `WelcomeMessage`
    (la lista `peers`) y sus campos son los mismos que carga `PresenceMessage`.
    Lo separamos en su propio tipo porque el roster del servidor lo va a usar
    como estructura de estado, igual que `Document` es el estado de un archivo.

    `path` es `None` cuando el cliente está conectado pero todavía no abrió
    ningún archivo: no está "presente" en ningún lado, así que no se muestra.
    `line` es 1-indexada (la primera línea es 1) porque así la piensa el humano
    y así la muestra la UI; 0 no tiene sentido como número de línea.
    """

    client_id: str
    name: str
    color: str
    path: str | None = None
    line: int = 1


@dataclass(frozen=True)
class WelcomeMessage:
    """Primer mensaje de presencia: el servidor te dice quién eres y quién más hay.

    Llega justo después del `InitMessage` (que trae el workspace). Mientras
    `InitMessage` responde "¿qué hay editado?", este responde "¿quién está aquí
    y dónde?". Va aparte y no se mete dentro de `InitMessage` a propósito: el
    snapshot del workspace es un contrato estable (la persistencia depende de
    que su forma no cambie), y la presencia tiene un ciclo de vida distinto.

    `you` es tu propia identidad asignada por el servidor. `peers` es la lista
    de los demás que ya están presentes en algún archivo, para que los pintes
    de inmediato sin esperar a que se muevan.
    """

    you: PresenceState
    peers: list[PresenceState] = field(default_factory=list)
    type: Literal["welcome"] = "welcome"


@dataclass(frozen=True)
class PresenceMessage:
    """"Estoy en `path`, línea `line`." Simétrico, como `UpdateMessage`.

    Del cliente al servidor: solo importan `path` y `line`; los campos de
    identidad van vacíos porque el servidor los rellena desde su registro (si el
    cliente pudiera mandar su propio `client_id` podría hacerse pasar por otro).
    Del servidor a los demás clientes: ya viene completo con identidad.
    """

    client_id: str
    name: str
    color: str
    path: str
    line: int
    type: Literal["presence"] = "presence"


@dataclass(frozen=True)
class LeaveMessage:
    """Alguien se desconectó: borren su marcador.

    Solo carga el `client_id` porque para quitar a alguien de la UI no hace
    falta nada más. Lo manda siempre el servidor (es el único que sabe cuándo
    una conexión muere); nunca lo manda un cliente.
    """

    client_id: str
    type: Literal["leave"] = "leave"


# --- Capa 4: ownership + edición tentativa ---
#
# La tesis del producto es prevenir la colisión con coordinación, no fusionar
# después. Ownership es esa coordinación: un path puede tener dueño. Si lo edita
# alguien que no es el dueño, el cambio NO se aplica: queda como una propuesta
# que el dueño aprueba o rechaza con un clic. "Editar primero, negociar después,
# aplicar al final."


@dataclass(frozen=True)
class ClaimMessage:
    """El cliente reclama ser dueño de un path.

    Andamiaje del prototipo: en el producto el ownership se asigna o se infiere
    (por configuración del equipo, por análisis semántico), no se reclama con un
    botón. Pero sin auth ni análisis todavía, un claim manual es la forma mínima
    de *tener* un dueño con quien demostrar el flujo tentativo. Solo lo manda el
    cliente; el servidor responde con un `OwnershipMessage`.
    """

    path: str
    type: Literal["claim"] = "claim"


@dataclass(frozen=True)
class OwnershipMessage:
    """Mapa completo `path -> client_id del dueño`. Simétrico como snapshot.

    Siempre lleva el mapa entero, no un cambio incremental: es idempotente y el
    cliente no tiene que reconstruir estado a partir de deltas. El servidor lo
    manda al conectar (tercer mensaje del handshake, después de `welcome`) y cada
    vez que el ownership cambia. Un path sin dueño simplemente no está en el mapa.
    """

    owners: dict[str, str] = field(default_factory=dict)
    type: Literal["ownership"] = "ownership"


@dataclass(frozen=True)
class Proposal:
    """Un cambio tentativo: contenido que alguien propone para un archivo ajeno.

    No es un mensaje: viaja embebido en `ProposalMessage`, igual que
    `PresenceState` viaja en `WelcomeMessage`. `id` es determinista
    (`path::author_id`): si el autor sigue tecleando, la nueva propuesta
    reemplaza a la anterior en vez de acumular basura. `content` es el archivo
    completo propuesto (esta capa no hace per-línea; eso es capa 5).
    """

    id: str
    path: str
    author_id: str
    author_name: str
    content: str


@dataclass(frozen=True)
class ProposalMessage:
    """El servidor avisa al dueño: "alguien propone cambios a tu archivo".

    Solo va servidor -> dueño. El autor no manda esto: manda un `UpdateMessage`
    normal y es el servidor quien decide que, por haber dueño distinto, ese
    update es tentativo y se convierte en propuesta.
    """

    proposal: Proposal
    type: Literal["proposal"] = "proposal"


@dataclass(frozen=True)
class ResolveMessage:
    """El dueño resuelve una propuesta: aprobar (`accept=True`) o rechazar.

    Cliente -> servidor. Aprobar aplica el contenido al workspace y lo difunde a
    todos (incluido el autor y el propio dueño, que deben converger). Rechazar
    la descarta y al autor se le reenvía el contenido autoritativo para que su
    edición tentativa local se revierta.
    """

    proposal_id: str
    accept: bool
    type: Literal["resolve"] = "resolve"


# --- Capa 6: análisis semántico de impacto ---


@dataclass(frozen=True)
class ImpactMessage:
    """El servidor avisa a un dueño: "un cambio ajeno afecta un archivo tuyo".

    Solo va servidor -> dueño del archivo afectado, y solo cuando el código
    parsea (ver analysis/python.py: nada de avisos por estados a medio
    escribir). Va agrupado por archivo afectado: "tu `affected_path` lo toca
    `author_name` porque cambió estos `symbols` en `source_path`". El cliente
    deduplica por (source_path, affected_path) y se queda con el último, igual
    que las propuestas: si el autor sigue tecleando no se acumulan avisos.

    No lleva identidad del receptor: se entrega dirigido a la conexión del
    dueño, no se difunde. Es "sin clickear un botón, lo hace solo" del README.
    """

    source_path: str
    author_name: str
    affected_path: str
    symbols: list[str]
    # Capa de "que no sea adorno": por cada símbolo, POR QUÉ su cambio te
    # importa (alineado 1:1 con `symbols`). "cambió la firma de X: …",
    # "se eliminó X". Sin esto el dev piensa "¿y esto a mí qué?". Default
    # vacío: un server viejo sin motivos no rompe el decode del cliente.
    motivos: list[str] = field(default_factory=list)
    type: Literal["impact"] = "impact"


# --- Capa 7: identidad real (login obligatorio) ---
#
# La app está CERRADA: al conectar, el servidor no manda nada hasta que el
# cliente se autentica. Tres formas de autenticarse, las tres cliente->server:
# registrarse, loguearse, o presentar un token de sesión firmado (auto-login
# al recargar). El servidor responde `auth_ok` (con un token fresco para
# guardar) o `auth_error`. Recién entonces empieza el handshake normal
# (init/welcome/ownership). La identidad ES el usuario, estable y persistida.


@dataclass(frozen=True)
class RegisterMessage:
    """Crear cuenta. Si el usuario es nuevo, queda registrado y autenticado."""

    username: str
    password: str
    type: Literal["register"] = "register"


@dataclass(frozen=True)
class LoginMessage:
    """Entrar con usuario+contraseña ya registrados."""

    username: str
    password: str
    type: Literal["login"] = "login"


@dataclass(frozen=True)
class SessionMessage:
    """Auto-login: presentar el token de sesión firmado guardado en el cliente.

    Reemplaza al token anónimo sin firmar de la identidad mínima. Si la firma
    es válida (la emitió este servidor) y el usuario aún existe, entra sin
    reescribir contraseña — eso es lo que hace que recargar no moleste.
    """

    token: str
    type: Literal["session"] = "session"


@dataclass(frozen=True)
class AuthOkMessage:
    """Servidor -> cliente: autenticado. `token` es de sesión, para guardar.

    El cliente lo persiste y lo presenta como `SessionMessage` al reconectar.
    """

    username: str
    token: str
    type: Literal["auth_ok"] = "auth_ok"


@dataclass(frozen=True)
class AuthErrorMessage:
    """Servidor -> cliente: el intento de autenticación falló. `reason` legible.

    La conexión NO se cierra: el cliente puede reintentar (otra contraseña,
    registrarse) sobre la misma conexión. Mensajes de app antes de
    autenticarse también responden con esto.
    """

    reason: str
    type: Literal["auth_error"] = "auth_error"


# --- Capa 8: integración con Git (solo lectura) ---


@dataclass(frozen=True)
class GitStatusMessage:
    """Servidor -> cliente: estado del repo del workspace.

    Solo lectura: rama, cuántos archivos sin commitear y los últimos commits.
    `available=False` si el server no tiene git habilitado o el binario no
    está. Se manda tras el handshake (si hay git) y cuando el cliente lo pide
    (`git_refresh`) — NO en cada tecla: correr git por pulsación sería un
    storm de subprocess. Que el estado quede algo viejo entre refrescos es
    aceptable: commiteas en tu terminal y das "actualizar".
    """

    available: bool
    branch: str = ""
    changes: int = 0
    commits: list[str] = field(default_factory=list)
    type: Literal["git_status"] = "git_status"


@dataclass(frozen=True)
class GitRefreshMessage:
    """Cliente -> servidor: "vuelve a consultar git y mándame el estado".

    Sin payload, solo lectura: re-pregunta el estado del repo.
    """

    type: Literal["git_refresh"] = "git_refresh"


@dataclass(frozen=True)
class CommitMessage:
    """Cliente -> servidor: commitea todo con este mensaje.

    Capa 9b: el commit YA NO se hace en la terminal del dev (en un deploy web
    no tienen terminal). Se hace desde la app; el servidor corre `git commit`
    con `autor = el usuario autenticado` (capa 7 nos da identidad real). Sigue
    sin haber push: el remoto/credenciales es la capa siguiente, aparte.
    """

    message: str
    type: Literal["commit"] = "commit"


@dataclass(frozen=True)
class GitResultMessage:
    """Servidor -> quien commiteó: resultado legible. `ok` éxito/fracaso.

    Feedback honesto: "commit creado", "no hay cambios", "git no disponible".
    Va dirigido a quien lo pidió; el cambio de estado del repo se difunde
    aparte con `git_status`.
    """

    ok: bool
    detail: str
    # Capa 21: en un push OK a la rama del equipo, link "abrir PR" de
    # GitHub (vacío si no es GitHub o no aplica). laidea NO crea el PR
    # —eso es API+scope, y "integración, no reemplazo"—: empuja la rama y
    # te da el link; el humano lo abre y GitHub hace el merge/review.
    pr_url: str = ""
    type: Literal["git_result"] = "git_result"


@dataclass(frozen=True)
class CloneMessage:
    """Cliente -> servidor: traé este repo y REEMPLAZÁ el workspace.

    Capa 10 (escalón mínimo). Destructivo: el cliente confirma antes de
    mandarlo. `username`/`token` son EFÍMEROS: se usan para este clone y NO
    se guardan en ningún lado (ver GitRepo._git_cred). Solo seguro sobre wss.
    """

    url: str
    username: str
    token: str
    type: Literal["clone"] = "clone"


@dataclass(frozen=True)
class PushMessage:
    """Cliente -> servidor: empujá el workspace al remoto.

    `url` vacío = usar el `origin` que dejó el clone. Credenciales efímeras,
    nunca guardadas. No fusiona: si el remoto avanzó, se rechaza y se dice.
    """

    username: str
    token: str
    url: str = ""
    type: Literal["push"] = "push"


# --- Capa 12: admin del workspace + reparto de ownership ---
#
# El bloqueo real para soltárselo a un equipo open source ya hecho: el
# ownership se auto-reclamaba por quien tocaba primero, lo cual en un
# proyecto existente no organiza nada. Hace falta alguien con autoridad que
# reparta las zonas desde un panel. Admin = el primer usuario registrado
# (UserStore.admin(); decisión mínima sin migrar el JSON).


@dataclass(frozen=True)
class AdminInfoMessage:
    """Servidor -> cliente: "¿sos admin? y esta es la gente registrada".

    Va una vez tras el handshake (después de `ownership`, ANTES del
    `git_status` opcional) a CADA cliente: así sabe si pinta el panel admin
    y con qué usuarios poblar el selector. Cierra el handshake fijo —
    siempre se manda, haya git o no. NO se re-difunde cuando alguien nuevo se registra: el admin
    recarga para refrescar la lista (mismo criterio que `git_refresh` — que
    quede algo viejo entre refrescos es aceptable, y evita inyectar mensajes
    a mitad del stream de todos). `users` es solo nombres (jamás sale de
    aquí un registro de contraseña). Un cliente no-admin igual lo recibe
    (con `is_admin=False`): el contrato es simétrico, el panel se oculta en
    el cliente y el server además ignora acciones admin de un no-admin.
    """

    is_admin: bool
    users: list[str] = field(default_factory=list)
    type: Literal["admin_info"] = "admin_info"


@dataclass(frozen=True)
class AdminAssignMessage:
    """Cliente (admin) -> servidor: asigná/quitá el dueño de `path`.

    `username` vacío = quitar dueño (revocar) — reusa `Ownership.liberar`,
    no hace falta pieza nueva para revocar. Con usuario, `Ownership.asignar`
    REASIGNA aunque ya tuviera dueño (el admin sí puede mover una zona; un
    `claim` normal no roba). El servidor verifica que quien lo manda sea el
    admin; si no, lo ignora en silencio (igual que el resto de acciones no
    autorizadas en capas 4/5/9 — no se delata el porqué). Tras aplicarlo,
    difunde el `OwnershipMessage` completo a todos, como cualquier cambio
    de ownership.
    """

    path: str
    username: str = ""
    type: Literal["admin_assign"] = "admin_assign"


@dataclass(frozen=True)
class AdminAssignManyMessage:
    """Cliente (admin) -> servidor: asigná/quitá el dueño de MUCHOS paths a la
    vez. Misma semántica que `AdminAssignMessage` (admin-only, `username`
    vacío = revocar, solo usuarios que existen) pero en lote.

    Por qué existe: la primera queja de uso real — repartir el ownership de
    un proyecto de 100 archivos uno por uno es inusable. Con esto el panel
    selecciona archivos/carpetas, elige un dueño UNA vez y manda todo junto;
    el server aplica el lote y difunde UN solo `OwnershipMessage` (no 100).
    Carpeta = sus archivos: el cliente expande la selección a paths
    concretos (el ownership sigue siendo por archivo; ownership por prefijo
    es un cambio de modelo deliberadamente diferido).
    """

    paths: list[str] = field(default_factory=list)
    username: str = ""
    type: Literal["admin_assign_many"] = "admin_assign_many"


# --- Capa 15: sistema multi-equipo (gate de equipo) ---
#
# Tras autenticarse, el usuario NO entra directo al workspace: primero el
# server le dice de qué equipos es. Sin equipo no ve nada (la app sigue
# cerrada un escalón más). Crea uno (queda admin) o redime un código de
# invitación. Recién con un equipo elegido empieza el handshake normal,
# scopeado a ESE equipo (otro equipo no existe para él).


@dataclass(frozen=True)
class LobbyMessage:
    """Servidor -> cliente: estás autenticado pero todavía no en un equipo.

    `teams` = los equipos a los que pertenecés [{id, nombre, rol}] (puede
    estar vacío: recién te registraste y nadie te invitó). `error` trae el
    motivo si la última acción de lobby falló (código inválido, nombre
    vacío). El cliente muestra: elegí un equipo / creá uno / pegá un código.
    """

    teams: list[dict] = field(default_factory=list)
    error: str = ""
    type: Literal["lobby"] = "lobby"


@dataclass(frozen=True)
class CreateTeamMessage:
    """Cliente -> servidor: creá un equipo nuevo; quedo como su admin."""

    nombre: str
    type: Literal["create_team"] = "create_team"


@dataclass(frozen=True)
class RedeemInviteMessage:
    """Cliente -> servidor: unime al equipo de este código (de un solo uso)."""

    code: str
    type: Literal["redeem_invite"] = "redeem_invite"


@dataclass(frozen=True)
class SelectTeamMessage:
    """Cliente -> servidor: entrar a este equipo (del que ya soy miembro)."""

    team_id: str
    type: Literal["select_team"] = "select_team"


@dataclass(frozen=True)
class TeamReadyMessage:
    """Servidor -> cliente: entraste a este equipo; lo que sigue (init/
    welcome/ownership/admin_info/git) es de ESTE equipo y de ningún otro."""

    team_id: str
    nombre: str
    rol: str
    type: Literal["team_ready"] = "team_ready"


@dataclass(frozen=True)
class CreateInviteMessage:
    """Cliente (admin del equipo) -> servidor: generá un código de invitación
    para mi equipo actual. Sólo el admin; un no-admin se ignora en silencio."""

    type: Literal["create_invite"] = "create_invite"


@dataclass(frozen=True)
class InviteCreatedMessage:
    """Servidor -> el admin que lo pidió: el código a compartir (un solo uso)."""

    code: str
    type: Literal["invite_created"] = "invite_created"


# Union de todos los tipos posibles. `decode` los distingue por el campo `type`.
# `PresenceState` y `Proposal` no entran: no son mensajes, son estado embebido.
Message = Union[
    InitMessage,
    UpdateMessage,
    DeleteMessage,
    SaveMessage,
    WelcomeMessage,
    PresenceMessage,
    LeaveMessage,
    ClaimMessage,
    OwnershipMessage,
    ProposalMessage,
    ResolveMessage,
    ImpactMessage,
    RegisterMessage,
    LoginMessage,
    SessionMessage,
    AuthOkMessage,
    AuthErrorMessage,
    GitStatusMessage,
    GitRefreshMessage,
    CommitMessage,
    GitResultMessage,
    CloneMessage,
    PushMessage,
    AdminInfoMessage,
    AdminAssignMessage,
    AdminAssignManyMessage,
    LobbyMessage,
    CreateTeamMessage,
    RedeemInviteMessage,
    SelectTeamMessage,
    TeamReadyMessage,
    CreateInviteMessage,
    InviteCreatedMessage,
]


def encode(message: Message) -> str:
    """Convierte un mensaje tipado a JSON listo para enviar por el socket.

    `asdict` viene de dataclasses y convierte la instancia a un dict recursivamente.
    El campo `type` se incluye automáticamente porque es un campo normal del
    dataclass (no un ClassVar). El receptor usará ese `type` para saber qué
    clase reconstruir.
    """
    return json.dumps(asdict(message))


def decode(raw: str) -> Message:
    """Parsea un string JSON y devuelve la instancia correcta según el `type`.

    Si la otra punta nos manda algo desconocido, levantamos error en vez de
    intentar adivinar. En producción quizás quieras loguearlo y descartar en vez
    de cerrar la conexión, pero ahora mismo gritar fuerte es lo correcto: si
    aparece un `type` que no esperábamos, es bug y queremos enterarnos.
    """
    data = json.loads(raw)
    kind = data.get("type")
    if kind == "init":
        return InitMessage(files=data.get("files", {}))
    if kind == "update":
        return UpdateMessage(path=data["path"], content=data["content"])
    if kind == "delete":
        return DeleteMessage(path=data["path"])
    if kind == "save":
        return SaveMessage(path=data["path"])
    if kind == "welcome":
        you = data["you"]
        return WelcomeMessage(
            you=PresenceState(**you),
            peers=[PresenceState(**p) for p in data.get("peers", [])],
        )
    if kind == "presence":
        # Del cliente solo exigimos `path` y `line`. Los campos de identidad
        # pueden no venir (el servidor los rellena); por eso usamos .get con
        # default en vez de indexar, así decode no explota con el mensaje que
        # manda el cliente. En sentido servidor->cliente sí vienen completos.
        return PresenceMessage(
            client_id=data.get("client_id", ""),
            name=data.get("name", ""),
            color=data.get("color", ""),
            path=data["path"],
            line=data["line"],
        )
    if kind == "leave":
        return LeaveMessage(client_id=data["client_id"])
    if kind == "claim":
        return ClaimMessage(path=data["path"])
    if kind == "ownership":
        return OwnershipMessage(owners=data.get("owners", {}))
    if kind == "proposal":
        p = data["proposal"]
        return ProposalMessage(proposal=Proposal(**p))
    if kind == "resolve":
        return ResolveMessage(
            proposal_id=data["proposal_id"], accept=data["accept"]
        )
    if kind == "impact":
        return ImpactMessage(
            source_path=data["source_path"],
            author_name=data["author_name"],
            affected_path=data["affected_path"],
            symbols=list(data.get("symbols", [])),
            motivos=list(data.get("motivos", [])),
        )
    if kind == "register":
        return RegisterMessage(
            username=data["username"], password=data["password"]
        )
    if kind == "login":
        return LoginMessage(
            username=data["username"], password=data["password"]
        )
    if kind == "session":
        return SessionMessage(token=data["token"])
    if kind == "auth_ok":
        return AuthOkMessage(username=data["username"], token=data["token"])
    if kind == "auth_error":
        return AuthErrorMessage(reason=data["reason"])
    if kind == "git_status":
        return GitStatusMessage(
            available=data["available"],
            branch=data.get("branch", ""),
            changes=data.get("changes", 0),
            commits=list(data.get("commits", [])),
        )
    if kind == "git_refresh":
        return GitRefreshMessage()
    if kind == "commit":
        return CommitMessage(message=data["message"])
    if kind == "git_result":
        return GitResultMessage(
            ok=data["ok"], detail=data["detail"],
            pr_url=data.get("pr_url", ""),
        )
    if kind == "clone":
        return CloneMessage(url=data["url"], username=data["username"], token=data["token"])
    if kind == "push":
        return PushMessage(username=data["username"], token=data["token"], url=data.get("url", ""))
    if kind == "admin_info":
        return AdminInfoMessage(
            is_admin=data["is_admin"], users=list(data.get("users", []))
        )
    if kind == "admin_assign":
        return AdminAssignMessage(
            path=data["path"], username=data.get("username", "")
        )
    if kind == "admin_assign_many":
        return AdminAssignManyMessage(
            paths=list(data.get("paths", [])),
            username=data.get("username", ""),
        )
    if kind == "lobby":
        return LobbyMessage(
            teams=list(data.get("teams", [])), error=data.get("error", "")
        )
    if kind == "create_team":
        return CreateTeamMessage(nombre=data["nombre"])
    if kind == "redeem_invite":
        return RedeemInviteMessage(code=data["code"])
    if kind == "select_team":
        return SelectTeamMessage(team_id=data["team_id"])
    if kind == "team_ready":
        return TeamReadyMessage(
            team_id=data["team_id"], nombre=data["nombre"], rol=data["rol"]
        )
    if kind == "create_invite":
        return CreateInviteMessage()
    if kind == "invite_created":
        return InviteCreatedMessage(code=data["code"])
    raise ValueError(f"tipo de mensaje desconocido: {kind!r}")
