"""Identidad real (capa 7). Login obligatorio, self-hosted, sin dependencias.

Núcleo puro (este paquete): registro de usuarios persistido, hashing de
contraseñas (PBKDF2, stdlib) y tokens de sesión firmados con HMAC. No conoce
la red ni el WebSocket — eso lo cablea el server (2/3). Reemplaza la identidad
mínima anónima por una real y estable, base del "autor" para la futura capa
de Git.
"""

from .oauth import (
    identidad_github,
    firmar_state,
    url_autorizacion,
    validar_state,
)
from .passwords import hash_password, verificar_password
from .store import UserStore, normalizar
from .tokens import crear_token, usuario_de_token

__all__ = [
    "UserStore",
    "crear_token",
    "firmar_state",
    "hash_password",
    "identidad_github",
    "normalizar",
    "url_autorizacion",
    "usuario_de_token",
    "validar_state",
    "verificar_password",
]
