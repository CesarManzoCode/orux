"""Capa 23: la capa de servicio de la API de operador (pura, sandbox).

Sin HTTP ni Postgres: MemTeamStore + un store de usuarios async mínimo.
Fija el comportamiento que la cáscara starlette solo traduce a HTTP (la
cáscara se verifica en VPS, igual que pyright/asyncpg)."""

from __future__ import annotations

import pytest

from orux.api import service
from orux.teams import MemTeamStore


class _UsersFake:
    def __init__(self, nombres):
        self._n = nombres

    async def usuarios(self):
        return list(self._n)


async def test_listar_usuarios() -> None:
    assert await service.listar_usuarios(_UsersFake(["ana", "be"])) == [
        "ana", "be"
    ]


async def test_listar_y_detalle_teams() -> None:
    s = MemTeamStore()
    t = await s.crear_equipo("Alpha", "ana")
    todos = await service.listar_teams(s)
    assert todos == [
        {"id": t["id"], "nombre": "Alpha", "plan": "free", "miembros": 1}
    ]
    det = await service.detalle_team(s, t["id"])
    assert det["plan"] == "free"
    assert det["miembros"] == [{"usuario": "ana", "rol": "admin"}]
    assert await service.detalle_team(s, "no-existe") is None


async def test_cambiar_plan_ok_invalido_y_inexistente() -> None:
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")
    tid = t["id"]
    # OK: acción de cobro manual -> premium.
    det = await service.cambiar_plan(s, tid, "premium")
    assert det["plan"] == "premium"
    assert await s.plan(tid) == "premium"
    # Plan inventado -> ValueError (la cáscara lo mapea a 400).
    with pytest.raises(ValueError, match="plan inválido"):
        await service.cambiar_plan(s, tid, "ultra")
    # Equipo inexistente -> None (404).
    assert await service.cambiar_plan(s, "nope", "free") is None


# --- Auth del operador por CUENTA (capa 23 + login) ----------------------
# Reusa las primitivas de capa 7 (UserStore=PBKDF2). El store real del
# deploy es PgUserStore (async); acá un wrapper async sobre el UserStore
# en memoria: misma superficie `verificar`, sin Postgres.

from orux.identity.store import UserStore  # noqa: E402


class _UsersAuth:
    def __init__(self) -> None:
        self._s = UserStore()  # en memoria

    def registrar(self, u: str, p: str) -> None:
        self._s.registrar(u, p)

    async def verificar(self, u: str, p: str) -> bool:
        return self._s.verificar(u, p)


async def test_login_operador_ok_emite_token_valido() -> None:
    users = _UsersAuth()
    users.registrar("ana", "s3creta")
    tok = await service.login_operador(users, "ana", "FIRMA", "ana", "s3creta")
    assert isinstance(tok, str) and tok
    # El token validado devuelve al operador.
    assert service.operador_de_token(tok, "ana", "FIRMA") == "ana"


async def test_login_operador_normaliza_el_usuario() -> None:
    users = _UsersAuth()
    users.registrar("ana", "pw")
    # admin_user con mayúsculas/espacios y login en minúsculas: misma cuenta.
    tok = await service.login_operador(users, "  Ana ", "K", "ana", "pw")
    assert tok is not None
    assert service.operador_de_token(tok, "ANA", "K") == "ana"


async def test_login_operador_rechaza_password_mala() -> None:
    users = _UsersAuth()
    users.registrar("ana", "buena")
    assert await service.login_operador(users, "ana", "K", "ana", "mala") is None


async def test_login_operador_rechaza_a_quien_no_es_el_operador() -> None:
    users = _UsersAuth()
    users.registrar("ana", "pw")
    users.registrar("bob", "pw")
    # bob existe y la pass es correcta, pero el operador es ana: None.
    assert await service.login_operador(users, "ana", "K", "bob", "pw") is None


async def test_login_operador_cerrado_si_no_configurado() -> None:
    users = _UsersAuth()
    users.registrar("ana", "pw")
    assert await service.login_operador(users, "", "K", "ana", "pw") is None
    assert await service.login_operador(users, "ana", "", "ana", "pw") is None


def test_operador_de_token_rechaza_falsos_y_no_configurado() -> None:
    tok = __import__(
        "orux.identity.tokens", fromlist=["crear_token"]
    ).crear_token("ana", "FIRMA")
    assert service.operador_de_token(tok, "ana", "FIRMA") == "ana"
    # Firma con otro secreto -> None (no lo emitió este server).
    assert service.operador_de_token(tok, "ana", "OTRO") is None
    # Token válido pero el usuario NO es el operador -> None.
    assert service.operador_de_token(tok, "bob", "FIRMA") is None
    # Basura / no configurado -> None (nunca explota).
    assert service.operador_de_token("no.es-un-token", "ana", "FIRMA") is None
    assert service.operador_de_token(tok, "", "FIRMA") is None
    assert service.operador_de_token(tok, "ana", "") is None
