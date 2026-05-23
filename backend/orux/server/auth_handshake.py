"""Compuerta de autenticación (capa 7) del server WS.

Lo que vive acá: el bucle de mensajes que corre ANTES de que el server
deje al cliente entrar a la app (lobby/sesión). Acepta register/login/
session, hace anti-fuerza-bruta y backoff por-conexión, y devuelve el
usuario normalizado (o `None` si el cliente cerró sin autenticarse).

Extraído de `sync.py` (modularización 2026-05-23). La función es libre
y recibe `server` como primer argumento (igual que `dispatch.py` e
`impacto.py`); usa los rate limits y los stores del SyncServer sin
crear acoplamiento extra.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING

from ..identity import normalizar, usuario_de_token
from ..protocol import (
    AuthErrorMessage,
    LoginMessage,
    RegisterMessage,
    SessionMessage,
    decode,
    encode,
)
from .config import _env_int
from .util import ip_cliente

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

    from .sync import SyncServer

logger = logging.getLogger(__name__)


async def autenticar(
    server: "SyncServer", websocket: "ServerConnection",
) -> str | None:
    """Compuerta de la capa 7: nada de app hasta autenticarse.

    Lee mensajes hasta que uno autentique (register/login/session) y
    devuelve el usuario normalizado. Mientras no lo logre responde
    `auth_error` y sigue escuchando en la MISMA conexión. None si la
    conexión se cierra sin autenticarse.

    Robustez (auditoría seguridad A1): la compuerta es la única
    superficie de fuerza bruta / DoS de almacenamiento. PBKDF2 240k
    limita el rate pero no lo impide. Defensa por-conexión (sin store
    compartido — eso sería otra capa): cada fallo suma un backoff
    creciente ANTES de volver a escuchar (un atacante que prueba miles
    de contraseñas sobre UN socket se vuelve lentísimo), y pasado un
    tope de fallos se corta el socket (lo obliga a re-hacer el handshake
    TCP/WS cada N intentos — fricción real, sin castigar al usuario que
    se equivoca un par de veces). El register exitoso retorna ya: el
    tope de fallos también acota el DoS de cuentas basura por conexión.
    """
    fallos = 0
    # Tan alto que un humano que se equivoca tecleando jamás lo alcanza,
    # tan bajo que el atacante re-paga el handshake muy seguido.
    MAX_FALLOS = 12

    async def _fallo(reason: str, code: str = "") -> bool:
        """Responde el error, aplica el backoff y dice si hay que cortar
        (tope alcanzado). El sleep va DESPUÉS de enviar el error: el
        cliente legítimo ve el mensaje al instante; el costo es del que
        sigue intentando.

        `code` (capa 35) es un label estable en inglés que el cliente
        traduce a su idioma. `reason` sigue viajando como fallback
        legible para clientes viejos o casos sin code definido.
        """
        nonlocal fallos
        fallos += 1
        await websocket.send(
            encode(AuthErrorMessage(reason=reason, code=code))
        )
        if fallos >= MAX_FALLOS:
            logger.warning(
                "auth: %d fallos en una conexión, se corta", fallos
            )
            return True
        # Lineal y modesto (0.3s, 0.6s, ...) tope 3s: invisible para un
        # error humano aislado, asfixiante para miles automatizados.
        await asyncio.sleep(min(3.0, 0.3 * fallos))
        return False

    async for raw in websocket:
        try:
            msg = decode(raw)
        except ValueError:
            if await _fallo("mensaje inválido", "invalid_message"):
                return None
            continue
        if isinstance(msg, RegisterMessage):
            # Anti-abuso: tope de registros por IP en ventana deslizante.
            # El registro es público; el backoff por-conexión no frena un
            # bot que hace connect -> register en bucle. Ver
            # `_throttle_registro`.
            if not server._throttle_registro(ip_cliente(websocket)):
                logger.warning("registro: tope por IP alcanzado")
                if await _fallo(
                    "demasiados registros desde tu red, esperá unos minutos",
                    "rate_limited_register",
                ):
                    return None
                continue
            # Cierre de registro tras N usuarios (BACKEND-AUDIT-0224).
            # Default 0 = sin tope (modo prototipo). En producción, el
            # operador setea ORUX_REGISTRO_CERRADO_TRAS=N para fijar el
            # primer N como cuentas legítimas y a partir de ahí solo se
            # entra por OAuth o invitación admin. NO mitiga el caso de
            # un atacante que se registra ANTES del admin real — eso
            # requiere bootstrap controlado (Day 0); el cierre evita la
            # segunda fase (atacante crea cuentas en serie post-bootstrap).
            cap = _env_int("ORUX_REGISTRO_CERRADO_TRAS", 0, 0, 1_000_000)
            if cap > 0:
                listar = getattr(server.users, "usuarios", None)
                if listar is not None:
                    try:
                        actuales = await listar() if inspect.iscoroutinefunction(listar) else listar()
                    except Exception as e:  # noqa: BLE001
                        # Si no podemos enumerar (p.ej. DB caída), tratamos
                        # como "no hay cap aplicable" — registro abierto
                        # antes que bloquear la plataforma. Pero NUNCA
                        # silencioso: el operador debe enterarse.
                        logger.warning(
                            "ORUX_REGISTRO_CERRADO_TRAS=%d activo pero "
                            "no puedo enumerar usuarios (%r); permito "
                            "registro este intento",
                            cap, e,
                        )
                        actuales = []
                    if len(actuales) >= cap:
                        if await _fallo(
                            "registro cerrado", "closed_registration"
                        ):
                            return None
                        continue
            try:
                return await server.users.registrar(msg.username, msg.password)
            except ValueError as e:
                # BACKEND-AUDIT-0004: 'ese usuario ya existe' filtra info
                # de enumeración. Detrás de un registro abierto el
                # atacante puede sondear cuentas. Reportamos un mensaje
                # genérico EXCEPTO para errores de FORMATO (charset,
                # longitud) que no filtran existencia y que el cliente
                # legítimo necesita para corregir su input.
                motivo_real = str(e)
                # El sub-caso "ya existe" lo enmascaramos para no
                # filtrar enumeración (BACKEND-AUDIT-0004); le ponemos
                # code para que el cliente lo traduzca. Los demás
                # errores de FORMATO (charset, longitud) viajan con
                # texto libre y SIN code — el cliente cae al `reason`
                # literal (que ya es legible para el usuario).
                if "ya existe" in motivo_real.lower():
                    razon, code_err = "no se pudo registrar", "register_failed"
                else:
                    razon, code_err = motivo_real, ""
                if await _fallo(razon, code_err):
                    return None
        elif isinstance(msg, LoginMessage):
            # Anti-fuerza-bruta: tope de logins por IP. El backoff
            # por-conexión se reinicia al reconectar; este tope no. Ver
            # `_throttle_login`.
            if not server._throttle_login(ip_cliente(websocket)):
                logger.warning("login: tope por IP alcanzado")
                if await _fallo(
                    "demasiados intentos desde tu red, esperá unos minutos",
                    "rate_limited",
                ):
                    return None
                continue
            if await server.users.verificar(msg.username, msg.password):
                return normalizar(msg.username)
            if await _fallo(
                "usuario o contraseña incorrectos", "bad_credentials"
            ):
                return None
        elif isinstance(msg, SessionMessage):
            # Epoch del usuario al verificar: tokens emitidos antes de
            # revocar (cambio de pwd / logout-all) dejan de valer
            # quirúrgicamente sin tirar todas las sesiones del server
            # (BACKEND-AUDIT-0002).
            user = None
            try:
                _ud = usuario_de_token(
                    msg.token, server._secret,
                    epoch_de=lambda u: 0,  # placeholder síncrono
                )
                if _ud is not None:
                    # Re-verifica el epoch contra el store async real.
                    epoch_actual = await server.users.epoch(_ud)
                    # Re-decodifica con un callable que devuelve el epoch
                    # ya consultado (un solo await; barato).
                    user = usuario_de_token(
                        msg.token, server._secret,
                        epoch_de=lambda u, _e=epoch_actual: _e,
                    )
            except Exception as e:
                logger.warning("error verificando sesión: %s", e)
            if user is not None and await server.users.existe(user):
                return user
            if await _fallo(
                "sesión inválida, inicia sesión", "invalid_session"
            ):
                return None
        else:
            if await _fallo(
                "debes autenticarte primero", "must_auth_first"
            ):
                return None
    return None
