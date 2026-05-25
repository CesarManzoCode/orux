"""Ports de identidad: tokens de sesión + flujo OAuth.

`SessionTokenPort` encapsula la emisión y verificación de tokens HMAC de
sesión. `OAuthPort` encapsula el flujo de proveedor externo (state CSRF +
URL de autorización + extracción de identidad del perfil).

Ambos son SYNC: las funciones subyacentes (`identity.tokens`,
`identity.oauth`) son puras y rápidas (hash sha256, urlencode, decode b64).
Async aquí sería ceremonia sin beneficio.

# Diseño: encapsular config externa, no convertir funciones a métodos

Las funciones `crear_token` / `usuario_de_token` / `firmar_state` /
`validar_state` siguen siendo PURAS (en `identity.tokens` e
`identity.oauth`): reciben el secret como parámetro, no tienen estado. El
valor de hex aquí no es "objetificar" funciones; es encapsular la **config
externa** (secret HMAC, client_id de OAuth, redirect_uri) dentro del adapter
para que el dominio no la conozca.

El adapter es delgado: cierra el secret y delega a la función pura. Tests del
dominio puro pueden seguir llamando las funciones libres sin un Port; los
callers externos (server, api) inyectan el Port.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class SessionTokenPort(Protocol):
    """Emite y verifica tokens de sesión HMAC.

    Implementación canónica: `adapters.identity.hmac_session.HmacSessionTokenAdapter`,
    que cierra el secret HMAC y delega a `identity.tokens.crear_token` /
    `usuario_de_token`.
    """

    def crear(
        self,
        username: str,
        ttl_seg: int | None = None,
        *,
        epoch: int = 0,
        kid: str | None = None,
    ) -> str: ...

    def usuario_de(
        self,
        token: str,
        *,
        epoch_de: Callable[[str], int] | None = None,
    ) -> str | None: ...


@runtime_checkable
class OAuthPort(Protocol):
    """Flujo OAuth de un proveedor (hoy: GitHub).

    Implementación canónica: `adapters.identity.github_oauth.GithubOAuthAdapter`,
    que cierra client_id, redirect_uri y secret del state CSRF, y delega a
    `identity.oauth` para la lógica pura. La parte que habla con la red
    (intercambiar `code` por token + leer perfil) vive en la cáscara HTTP
    (`api/app.py`) y es inyectada al adapter — el adapter no hace I/O.
    """

    def url_autorizacion(self, state: str, scope: str | None = None) -> str: ...

    def firmar_state(self, ahora: float | None = None) -> str: ...

    def validar_state(
        self,
        state: str,
        max_edad: float = 120.0,
        ahora: float | None = None,
    ) -> bool: ...

    def identidad(self, perfil: dict) -> str: ...
