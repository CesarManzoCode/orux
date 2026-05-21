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

# Tope HARD del frame entero antes de decode (BACKEND-AUDIT-0033 / -0271). El
# server WS también pasa `max_size` a `serve(...)`; este es la defensa en el
# protocol module si llega a llamarse desde otro contexto. Subirlo aquí es
# rompedor (un commit con un patch gordo entra en updates).
MAX_FRAME_BYTES = 2 * 1024 * 1024  # 2 MB

# Topes por campo individual: cap simétrico entre lo que el server acepta y
# lo que un cliente legítimo podría mandar. Sin estos, un `content` de 1.9MB
# pasa el frame check y se procesa entero. Calibrados para casos legítimos:
# un archivo de 1MB es muy holgado (LSP/treesitter empieza a chillar antes).
_MAX_CONTENT = 1024 * 1024       # 1 MB
_MAX_MESSAGE = 8 * 1024          # 8 KB (commit message, reason, etc.)
_MAX_PATH = 1024                 # 1 KB (suficiente para nested dirs)
_MAX_USERNAME = 128
_MAX_PASSWORD = 256              # > passwords.py _PWD_MAX pero defensivo
_MAX_TOKEN = 4096                # tokens HMAC + base64 caben holgados
_MAX_URL = 2048
_MAX_LIST_ITEMS = 1024           # listas de strings (peers, symbols, etc.)
_MAX_STRING_FIELD = 1024         # campos cortos genéricos


class ProtocolError(ValueError):
    """Error de protocolo: el mensaje no respeta el contrato (forma, tamaño,
    tipo). Se sube como `ValueError` para que los catch del server existente
    sigan funcionando. Mensaje SIEMPRE legible para devolver al cliente."""


def _str(v: object, *, max_len: int = _MAX_STRING_FIELD,
         campo: str = "campo", permitir_vacio: bool = True) -> str:
    """Lee un campo string del dict, valida tipo y tope. Devuelve "" si falta
    o es None y `permitir_vacio` (default). Levanta `ProtocolError` con un
    mensaje legible si el tipo o el tamaño no cuadran."""
    if v is None:
        if permitir_vacio:
            return ""
        raise ProtocolError(f"falta '{campo}'")
    if not isinstance(v, str):
        raise ProtocolError(f"'{campo}' debe ser texto")
    if len(v) > max_len:
        raise ProtocolError(
            f"'{campo}' excede el tope ({len(v)} > {max_len} bytes)"
        )
    return v


def _int(v: object, *, default: int = 0, minimo: int | None = None,
         maximo: int | None = None, campo: str = "campo") -> int:
    """Lee un entero defensivamente. Acepta None (-> default), int real
    (no bool), o string convertible. Aplica clamp si min/max."""
    if v is None:
        return default
    if isinstance(v, bool):
        raise ProtocolError(f"'{campo}' debe ser entero, no bool")
    if isinstance(v, int):
        n = v
    elif isinstance(v, str):
        try:
            n = int(v)
        except ValueError:
            raise ProtocolError(f"'{campo}' debe ser entero") from None
    else:
        raise ProtocolError(f"'{campo}' debe ser entero")
    if minimo is not None and n < minimo:
        n = minimo
    if maximo is not None and n > maximo:
        n = maximo
    return n


def _bool(v: object, *, default: bool = False, campo: str = "campo") -> bool:
    """Lee un booleano. Estricto: solo True/False; un int=1 no cuenta para
    evitar confusiones de tipo."""
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    raise ProtocolError(f"'{campo}' debe ser true/false")


def _list_str(v: object, *, max_items: int = _MAX_LIST_ITEMS,
              max_len: int = _MAX_STRING_FIELD, campo: str = "campo") -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list):
        raise ProtocolError(f"'{campo}' debe ser lista")
    if len(v) > max_items:
        raise ProtocolError(f"'{campo}' excede {max_items} elementos")
    out: list[str] = []
    for it in v:
        if not isinstance(it, str):
            raise ProtocolError(f"elementos de '{campo}' deben ser texto")
        if len(it) > max_len:
            raise ProtocolError(f"un elemento de '{campo}' excede {max_len} bytes")
        out.append(it)
    return out


def _dict_str(v: object, *, max_items: int = 4096, max_key: int = _MAX_PATH,
              max_val: int = _MAX_CONTENT, campo: str = "campo") -> dict[str, str]:
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise ProtocolError(f"'{campo}' debe ser objeto")
    if len(v) > max_items:
        raise ProtocolError(f"'{campo}' excede {max_items} elementos")
    out: dict[str, str] = {}
    for k, val in v.items():
        if not isinstance(k, str) or not isinstance(val, str):
            raise ProtocolError(f"'{campo}' debe ser objeto texto->texto")
        if len(k) > max_key:
            raise ProtocolError(f"una clave de '{campo}' excede {max_key} bytes")
        if len(val) > max_val:
            raise ProtocolError(f"un valor de '{campo}' excede {max_val} bytes")
        out[k] = val
    return out


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
    # Capa 24: impacto transitivo. La CADENA de hops desde el cambio
    # original hasta este archivo ("models.py:Usuario" -> "factory.py:
    # make_user" -> …): el porqué de la onda, legible. Vacío = impacto
    # DIRECTO (free / capas 17-21): byte-compat con clientes/tests viejos.
    cadena: list[str] = field(default_factory=list)
    # Capa 24d: severidad por símbolo (1:1 con `symbols`): "alta"|"media"|
    # "baja". El dueño prioriza el triage. Vacío = byte-compat con
    # clientes/tests viejos (el cliente cae a "media").
    severidades: list[str] = field(default_factory=list)
    type: Literal["impact"] = "impact"


# --- Capa 7: identidad real (login obligatorio) ---
#
# La app está CERRADA: al conectar, el servidor no manda nada hasta que el
# cliente se autentica. Tres formas de autenticarse, las tres cliente->server:
# registrarse, loguearse, o presentar un token de sesión firmado (auto-login
# al recargar). El servidor responde `auth_ok` (con un token fresco para
# guardar) o `auth_error`. Recién entonces empieza el handshake normal
# (init/welcome/ownership). La identidad ES el usuario, estable y persistida.


@dataclass(frozen=True, repr=False)
class RegisterMessage:
    """Crear cuenta. Si el usuario es nuevo, queda registrado y autenticado.

    `repr=False` + `__repr__` enmascarado para que un traceback o un
    `logger.debug(msg)` jamás imprima el password (BACKEND-AUDIT-0034)."""

    username: str
    password: str
    type: Literal["register"] = "register"

    def __repr__(self) -> str:
        return f"RegisterMessage(username={self.username!r}, password='***')"


@dataclass(frozen=True, repr=False)
class LoginMessage:
    """Entrar con usuario+contraseña ya registrados."""

    username: str
    password: str
    type: Literal["login"] = "login"

    def __repr__(self) -> str:
        return f"LoginMessage(username={self.username!r}, password='***')"


@dataclass(frozen=True, repr=False)
class SessionMessage:
    """Auto-login: presentar el token de sesión firmado guardado en el cliente.

    Reemplaza al token anónimo sin firmar de la identidad mínima. Si la firma
    es válida (la emitió este servidor) y el usuario aún existe, entra sin
    reescribir contraseña — eso es lo que hace que recargar no moleste.
    """

    token: str
    type: Literal["session"] = "session"

    def __repr__(self) -> str:
        return "SessionMessage(token='***')"


@dataclass(frozen=True, repr=False)
class AuthOkMessage:
    """Servidor -> cliente: autenticado. `token` es de sesión, para guardar.

    El cliente lo persiste y lo presenta como `SessionMessage` al reconectar.
    """

    username: str
    token: str
    type: Literal["auth_ok"] = "auth_ok"

    def __repr__(self) -> str:
        return f"AuthOkMessage(username={self.username!r}, token='***')"


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
    # GitHub (vacío si no es GitHub o no aplica). orux NO crea el PR
    # —eso es API+scope, y "integración, no reemplazo"—: empuja la rama y
    # te da el link; el humano lo abre y GitHub hace el merge/review.
    pr_url: str = ""
    type: Literal["git_result"] = "git_result"


@dataclass(frozen=True, repr=False)
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

    def __repr__(self) -> str:
        return f"CloneMessage(url={self.url!r}, username={self.username!r}, token='***')"


@dataclass(frozen=True, repr=False)
class PushMessage:
    """Cliente -> servidor: empujá el workspace al remoto.

    `url` vacío = usar el `origin` que dejó el clone. Credenciales efímeras,
    nunca guardadas. No fusiona: si el remoto avanzó, se rechaza y se dice.
    """

    username: str
    token: str
    url: str = ""
    # Capa 21b: rama destino ELEGIBLE. Vacío = la rama de publicación del
    # equipo (default seguro, force-with-lease + PR). Cualquier otra (p.ej.
    # "main") = push directo SIN forzar (capa 10: non-ff honesto, nunca
    # pisa historia compartida). orux decide force-vs-no según si es su
    # propia rama; el usuario solo elige el destino.
    rama: str = ""
    type: Literal["push"] = "push"

    def __repr__(self) -> str:
        return (
            f"PushMessage(username={self.username!r}, token='***', "
            f"url={self.url!r}, rama={self.rama!r})"
        )


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
