"""Tokens de sesión firmados. Pieza pura de la capa 7.

El problema que resuelve: hoy (identidad mínima) el cliente manda un token
anónimo SIN firmar en la URL — cualquiera puede inventar el de otro. Aquí el
token va firmado con HMAC y un secreto del servidor: el cliente lo guarda y lo
presenta al reconectar, y el servidor confirma que lo emitió él y no fue
manipulado.

Robustez (auditoría seguridad M1 + auditoría posterior): el token caduca y
puede invalidarse por usuario sin rotar el secreto global.

- `exp` (epoch UTC) ⇒ ventana acotada si se filtra. Tokens sin `exp` se siguen
  ACEPTANDO con warning (mitigación BACKEND-AUDIT-0001): degradar es la única
  forma de no tumbar sesiones vivas; cuando el parque rote, suben.
- `epoch` por usuario ⇒ revocación quirúrgica (BACKEND-AUDIT-0002). El
  `UserStore` lleva un contador por usuario: cambiar contraseña o llamar a
  `revocar_sesiones(user)` lo incrementa, y los tokens viejos dejan de matchear.
  Sin esto, una sesión filtrada solo se cerraba rotando el secreto del server
  — y eso tira TODAS las sesiones a la vez.
- `kid` (key id) en el payload ⇒ rotación atómica del secret (BACKEND-AUDIT-0022).
  `usuario_de_token` acepta una lista de secretos (current + previous) y elige
  por `kid`; sin `kid` cae al primero como antes.
- Domain separation HMAC (BACKEND-AUDIT-0023): la firma incluye un prefijo
  fijo `orux-session\x00` para que un atacante no confunda un token de
  sesión con un state de OAuth si por accidente comparten secret.

Formato: `<payload_b64url>.<hmac_hex>`. El payload es un dict serializado.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import time
from hashlib import sha256
from typing import Callable, Iterable

logger = logging.getLogger(__name__)


# AUDITORIA-SEGURIDAD 2026-05-25 A-HTTP-02: tokens sin `exp` ya NO se aceptan
# por defecto. El flag de opt-out existe para entornos legacy en migración
# (en orux ya rotó el parque), pero requiere setearlo a propósito.
def _aceptar_tokens_sin_exp() -> bool:
    return os.environ.get("ORUX_ALLOW_NONEXPIRING_TOKENS", "") == "1"


# Clamp mínimo del TTL emitido. Sin esto, un caller mal configurado podía
# emitir tokens con ttl=1s o 10s que en la práctica son una eternidad
# (cualquier verificación los acepta). 3600s = 1h es el piso de utilidad.
_TTL_MIN_SEG = 3600

# Prefijo de dominio para HMAC. Sin esto, si el secreto se comparte entre el
# token de sesión y otro contexto (OAuth state), una firma de un contexto
# puede pasar por la del otro (BACKEND-AUDIT-0023). El byte 0 es separador
# que no puede aparecer en el payload b64.
_DOMAIN_SESSION = b"orux-session\x00"


def _b64(data: bytes) -> str:
    # urlsafe y sin '=' para que el token viaje limpio en una URL/JSON.
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _firma(payload_b64: str, secret: str) -> str:
    msg = _DOMAIN_SESSION + payload_b64.encode("ascii")
    return hmac.new(secret.encode("utf-8"), msg, sha256).hexdigest()


def _firma_legacy(payload_b64: str, secret: str) -> str:
    """Firma anterior al fix de domain separation (BACKEND-AUDIT-0023). Sin
    prefijo de dominio. Se mantiene SOLO para verificar tokens emitidos
    antes del fix; cuando el parque rote, se puede eliminar."""
    return hmac.new(
        secret.encode("utf-8"), payload_b64.encode("ascii"), sha256
    ).hexdigest()


def crear_token(
    username: str,
    secret: str,
    ttl_seg: int | None = None,
    *,
    epoch: int = 0,
    kid: str | None = None,
) -> str:
    """Emite un token de sesión firmado para `username`.

    - `ttl_seg`: segundos de validez. >0 ⇒ el token caduca a `now + ttl_seg`.
      None o 0 ⇒ sin `exp` (legacy: solo para tests o si el operador rompe la
      regla a propósito; en runtime SIEMPRE pasamos ttl_seg explícito).
    - `epoch`: contador de sesiones del usuario al emitir (lo lleva el store).
      Si después se revoca la sesión incrementando el contador, este token
      deja de ser válido aunque el `exp` no haya pasado.
    - `kid`: id del secreto que firmó. Permite rotación atómica: durante la
      ventana de rotación, `usuario_de_token` valida contra `secrets[kid]`.

    `username` vacío levanta `ValueError`: antes el productor lo aceptaba y
    el verificador lo rechazaba (BACKEND-AUDIT-0024).
    """
    if not isinstance(username, str) or not username:
        raise ValueError("usuario inválido para emitir token")
    datos: dict[str, object] = {"user": username, "epoch": int(epoch)}
    if ttl_seg:
        # AUDITORIA-SEGURIDAD 2026-05-25 A-HTTP-02: clampar mínimo a 1h
        # para ttls positivos chicos (un caller con ttl_seg=10 generaba
        # tokens cuasi-eternos por la latencia de chequeo). Los ttls
        # NEGATIVOS no se clampean — emiten un token con exp en el
        # pasado (token muerto desde el momento de emisión), útil para
        # tests y para revocaciones explícitas.
        n = int(ttl_seg)
        ttl_efectivo = max(_TTL_MIN_SEG, n) if n > 0 else n
        datos["exp"] = int(time.time()) + ttl_efectivo
    if kid:
        datos["kid"] = kid
    payload_b64 = _b64(json.dumps(datos, sort_keys=True).encode("utf-8"))
    return f"{payload_b64}.{_firma(payload_b64, secret)}"


def usuario_de_token(
    token: str,
    secret: str | Iterable[str] | dict[str, str],
    *,
    epoch_de: Callable[[str], int] | None = None,
) -> str | None:
    """Devuelve el usuario si el token es válido; si no, None.

    `secret` puede ser:
    - un string (modo histórico),
    - una lista/iter de strings (intenta cada uno; útil durante rotación),
    - un dict {kid: secret} (selecciona por `kid` del payload; cae a "current"
      si no hay match).

    `epoch_de(user) -> int`: si se pasa, debe devolver el contador de sesiones
    autoritativo del usuario. El token se rechaza si su `epoch` < el actual
    (la sesión fue revocada al cambiar la contraseña, p.ej.).

    `None` cubre todo lo que no sea un token legítimo emitido con un `secret`
    aceptado: formato roto, firma falsa, payload manipulado, sesión revocada,
    expirado. Quien llame trata None como "no autenticado", nunca como
    excepción.
    """
    try:
        payload_b64, firma = token.split(".", 1)
    except (ValueError, AttributeError):
        return None

    # Materializa la lista de secrets a probar, respetando `kid` si se pasó.
    secretos_a_probar: list[str] = []
    try:
        datos_preview = json.loads(_unb64(payload_b64))
    except (ValueError, TypeError):
        return None
    if not isinstance(datos_preview, dict):
        return None
    kid = datos_preview.get("kid")
    if isinstance(secret, dict):
        if isinstance(kid, str) and kid in secret:
            secretos_a_probar.append(secret[kid])
        # Fallback: "current" si está, o todos
        if "current" in secret and secret["current"] not in secretos_a_probar:
            secretos_a_probar.append(secret["current"])
        for v in secret.values():
            if v not in secretos_a_probar:
                secretos_a_probar.append(v)
    elif isinstance(secret, str):
        secretos_a_probar.append(secret)
    else:
        secretos_a_probar.extend(secret)

    # Firma debe coincidir con alguna de las pasadas (current + anteriores).
    # Probamos también `_firma_legacy` para tokens emitidos antes de domain
    # separation: si el token es legacy, valida; si no, rechaza.
    if not any(
        hmac.compare_digest(firma, _firma(payload_b64, s))
        or hmac.compare_digest(firma, _firma_legacy(payload_b64, s))
        for s in secretos_a_probar
    ):
        return None

    try:
        datos = json.loads(_unb64(payload_b64))
        usuario = datos["user"]
        if not (isinstance(usuario, str) and usuario):
            return None

        exp = datos.get("exp")
        # AUDITORIA-SEGURIDAD 2026-05-25 A-HTTP-02: `exp` ausente ya NO se
        # acepta salvo flag explícito `ORUX_ALLOW_NONEXPIRING_TOKENS=1`.
        # Antes el server aceptaba con warning, lo que daba sesiones
        # potencialmente eternas a tokens viejos sin expiración. El flag
        # existe SOLO para entornos legacy en migración (en orux ya rotó
        # el parque a tokens con ttl). `exp` debe ser entero estricto
        # (no float / no bool — un atacante con la firma podría intentar
        # `exp=inf` BACKEND-AUDIT-0029).
        if exp is None:
            if not _aceptar_tokens_sin_exp():
                return None
            logger.warning(
                "token aceptado sin exp para usuario=%s "
                "(ORUX_ALLOW_NONEXPIRING_TOKENS=1)", usuario,
            )
        else:
            if not isinstance(exp, int) or isinstance(exp, bool):
                return None
            if time.time() >= exp:
                return None

        # Epoch chequeado contra el del usuario: si el store dice que el
        # usuario revocó/cambió pwd, los tokens viejos NO valen aunque su
        # exp no haya pasado (BACKEND-AUDIT-0002).
        if epoch_de is not None:
            try:
                actual = int(epoch_de(usuario))
            except (TypeError, ValueError):
                return None
            tok_epoch = datos.get("epoch", 0)
            if not isinstance(tok_epoch, int) or isinstance(tok_epoch, bool):
                return None
            if tok_epoch < actual:
                return None

        return usuario
    except (ValueError, KeyError, TypeError):
        return None
