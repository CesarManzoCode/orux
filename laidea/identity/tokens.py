"""Tokens de sesión firmados. Pieza pura de la capa 7.

El problema que resuelve: hoy (identidad mínima) el cliente manda un token
anónimo SIN firmar en la URL — cualquiera puede inventar el de otro. Aquí el
token va firmado con HMAC y un secreto del servidor: el cliente lo guarda y lo
presenta al reconectar, y el servidor confirma que lo emitió él y no fue
manipulado. No es una sesión completa (sin expiración todavía: deuda
consciente del prototipo, fácil de sumar porque el payload es estructurado).

Formato: `<payload_b64url>.<hmac_hex>`. El payload hoy solo lleva el usuario;
es un dict serializado para poder añadir `exp` u otros campos sin cambiar el
formato del token.
"""

from __future__ import annotations

import base64
import hmac
import json
from hashlib import sha256


def _b64(data: bytes) -> str:
    # urlsafe y sin '=' para que el token viaje limpio en una URL/JSON.
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _firma(payload_b64: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), payload_b64.encode("ascii"), sha256
    ).hexdigest()


def crear_token(username: str, secret: str) -> str:
    """Emite un token de sesión firmado para `username`."""
    payload_b64 = _b64(json.dumps({"user": username}).encode("utf-8"))
    return f"{payload_b64}.{_firma(payload_b64, secret)}"


def usuario_de_token(token: str, secret: str) -> str | None:
    """Devuelve el usuario si el token es válido y la firma cuadra; si no, None.

    `None` cubre todo lo que no sea un token legítimo emitido con este
    `secret`: formato roto, firma falsa, payload manipulado. Quien llame trata
    None como "no autenticado", nunca como excepción.
    """
    try:
        payload_b64, firma = token.split(".", 1)
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(firma, _firma(payload_b64, secret)):
        return None
    try:
        datos = json.loads(_unb64(payload_b64))
        usuario = datos["user"]
        return usuario if isinstance(usuario, str) and usuario else None
    except (ValueError, KeyError, TypeError):
        return None
