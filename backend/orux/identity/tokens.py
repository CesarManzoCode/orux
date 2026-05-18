"""Tokens de sesión firmados. Pieza pura de la capa 7.

El problema que resuelve: hoy (identidad mínima) el cliente manda un token
anónimo SIN firmar en la URL — cualquiera puede inventar el de otro. Aquí el
token va firmado con HMAC y un secreto del servidor: el cliente lo guarda y lo
presenta al reconectar, y el servidor confirma que lo emitió él y no fue
manipulado.

Robustez (auditoría seguridad M1): el token ahora caduca. Antes vivía para
siempre — uno filtrado (logs, historial del navegador, copy/paste) era una
llave permanente, sin forma de revocarlo salvo rotar el secreto (que tira
TODAS las sesiones). Ahora el payload lleva `exp` (epoch UTC) y se rechaza
pasado ese instante: una fuga tiene ventana acotada. Sin lista de revocación
activa todavía (rotar el secreto sigue siendo el botón de pánico global);
acotar la vida del token es la mitigación barata que el formato ya soportaba.

Migración sin romper sesiones vivas: un token LEGACY (sin `exp`) se sigue
aceptando como antes. Los emitidos de ahora en más llevan `exp`; cuando el
parque rote naturalmente, todos caducan. Opt-out explícito: `ttl_seg=0` (o
None) emite sin `exp` (mismo comportamiento histórico, por si el operador lo
necesita).

Formato: `<payload_b64url>.<hmac_hex>`. El payload es un dict serializado
(`user`, opcional `exp`): añadir campos no cambia el formato del token.
"""

from __future__ import annotations

import base64
import hmac
import json
import time
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


def crear_token(
    username: str, secret: str, ttl_seg: int | None = None
) -> str:
    """Emite un token de sesión firmado para `username`.

    `ttl_seg`: segundos de validez. Si es un entero > 0, el token lleva
    `exp = ahora + ttl_seg` y caduca. None o 0 = sin `exp` (token legacy,
    no caduca: opt-out explícito del operador).
    """
    datos: dict[str, object] = {"user": username}
    if ttl_seg:
        datos["exp"] = int(time.time()) + int(ttl_seg)
    payload_b64 = _b64(json.dumps(datos).encode("utf-8"))
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
        if not (isinstance(usuario, str) and usuario):
            return None
        exp = datos.get("exp")
        # `exp` ausente = token legacy (pre-robustez): se sigue aceptando
        # para no tumbar sesiones vivas. Presente: debe ser un número y NO
        # haber pasado. Un `exp` corrupto (no numérico) => token inválido,
        # no "sin expiración" (fail-closed: ante la duda, no autentica).
        if exp is not None:
            if not isinstance(exp, (int, float)) or isinstance(exp, bool):
                return None
            if time.time() >= exp:
                return None
        return usuario
    except (ValueError, KeyError, TypeError):
        return None
