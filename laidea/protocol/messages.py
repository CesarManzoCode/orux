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


# Union de todos los tipos posibles. `decode` los distingue por el campo `type`.
# Si en el futuro agregamos DeleteMessage, OwnershipChangeMessage, etc., se
# suman aquí. `PresenceState` no entra: no es un mensaje, es estado embebido.
Message = Union[InitMessage, UpdateMessage, WelcomeMessage, PresenceMessage, LeaveMessage]


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
    raise ValueError(f"tipo de mensaje desconocido: {kind!r}")
