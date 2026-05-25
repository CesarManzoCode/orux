"""Inbound WebSocket adapter: traduce mensajes WS ↔ use cases.

`SyncServer` orquesta el ciclo de conexión, lobby, dispatch a use cases y
broadcast. Los handlers (dispatch.py) son translate-layer puro: decode WS →
Command → use case → Result → encode/send.
"""

from .sync import SyncServer

__all__ = ["SyncServer"]
