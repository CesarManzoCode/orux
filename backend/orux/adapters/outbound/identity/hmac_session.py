"""`HmacSessionTokenAdapter`: cumple `SessionTokenPort` cerrando el secret.

Delegado a las funciones puras `identity.tokens.crear_token` /
`usuario_de_token`. El adapter sólo cierra el secret HMAC (config externa)
para que el dominio no lo conozca.

`secret` puede ser un string (modo histórico), una lista (rotación con
fallback ordenado) o un dict `{kid: secret}` (rotación atómica por kid).
"""

from __future__ import annotations

from typing import Callable, Iterable

from orux.identity.tokens import crear_token, usuario_de_token


class HmacSessionTokenAdapter:
    def __init__(
        self, secret: str | Iterable[str] | dict[str, str],
    ) -> None:
        self._secret = secret

    def crear(
        self,
        username: str,
        ttl_seg: int | None = None,
        *,
        epoch: int = 0,
        kid: str | None = None,
    ) -> str:
        # Para `crear_token` el `secret` debe ser un string puntual; si el
        # adapter se construyó con dict/lista (rotación), elegimos el
        # "current" o el primero. La verificación SÍ acepta varios.
        s = self._secret
        if isinstance(s, dict):
            s = s.get("current") or next(iter(s.values()))
        elif not isinstance(s, str):
            s = next(iter(s))
        return crear_token(username, s, ttl_seg, epoch=epoch, kid=kid)

    def usuario_de(
        self,
        token: str,
        *,
        epoch_de: Callable[[str], int] | None = None,
    ) -> str | None:
        return usuario_de_token(token, self._secret, epoch_de=epoch_de)
