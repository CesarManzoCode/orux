"""Tipos de mensajes que viajan por el WebSocket entre cliente y servidor."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Union


@dataclass(frozen=True)
class InitMessage:
    content: str
    type: Literal["init"] = "init"


@dataclass(frozen=True)
class UpdateMessage:
    content: str
    type: Literal["update"] = "update"


Message = Union[InitMessage, UpdateMessage]


def encode(message: Message) -> str:
    return json.dumps({"type": message.type, "content": message.content})


def decode(raw: str) -> Message:
    data = json.loads(raw)
    kind = data.get("type")
    if kind == "init":
        return InitMessage(content=data["content"])
    if kind == "update":
        return UpdateMessage(content=data["content"])
    raise ValueError(f"tipo de mensaje desconocido: {kind!r}")
