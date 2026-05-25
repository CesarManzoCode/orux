"""`GithubOAuthAdapter`: cumple `OAuthPort` cerrando client_id, redirect_uri
y secret CSRF.

Delegado a las funciones puras de `identity.oauth`. La parte de red
(intercambiar `code` por access token y leer el perfil de GitHub) NO está
acá: vive en la cáscara HTTP (`api/app.py`). Este adapter solo orquesta la
lógica pura.
"""

from __future__ import annotations

from orux.identity.oauth import (
    SCOPE,
    firmar_state,
    identidad_github,
    url_autorizacion,
    validar_state,
)


class GithubOAuthAdapter:
    def __init__(
        self,
        client_id: str,
        redirect_uri: str,
        state_secret: str,
    ) -> None:
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._state_secret = state_secret

    def url_autorizacion(
        self, state: str, scope: str | None = None,
    ) -> str:
        return url_autorizacion(
            self._client_id, self._redirect_uri, state, scope or SCOPE,
        )

    def firmar_state(self, ahora: float | None = None) -> str:
        return firmar_state(self._state_secret, ahora=ahora)

    def validar_state(
        self,
        state: str,
        max_edad: float = 120.0,
        ahora: float | None = None,
    ) -> bool:
        return validar_state(
            state, self._state_secret, max_edad=max_edad, ahora=ahora,
        )

    def identidad(self, perfil: dict) -> str:
        return identidad_github(perfil)
