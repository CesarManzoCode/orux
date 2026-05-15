"""Tipos de mensajes que viajan por el WebSocket entre cliente y servidor.

El protocolo es el "contrato" entre las dos puntas del sistema. Tanto el servidor
como el cliente tienen que estar de acuerdo en qué mensajes se mandan y qué forma
tienen. Por eso vive en su propio módulo: si un día cambiamos cómo se envía un
update, este es el único archivo que el servidor y el cliente tienen que coordinar.

Capa 1 (esta): el documento dejó de ser un solo string y pasó a ser un mapa de
`path -> contenido`. Cada mensaje de update ahora dice a qué archivo se refiere.
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


# Union de todos los tipos posibles. Si en el futuro agregamos PresenceMessage,
# DeleteMessage, OwnershipChangeMessage, etc., se suman aquí y `decode` aprende a
# distinguirlos por el campo `type`.
Message = Union[InitMessage, UpdateMessage]


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
    raise ValueError(f"tipo de mensaje desconocido: {kind!r}")
