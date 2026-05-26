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

    async def epoch(self, u: str) -> int:
        # AUDITORIA-SEGURIDAD 2026-05-25 A-AUTH-01: operador_de_token ahora
        # consulta el epoch del store. Exponerlo acá emula PgUserStore.
        return self._s.epoch(u)

    def revocar_sesiones(self, u: str) -> None:
        self._s.revocar_sesiones(u)


async def test_login_operador_ok_emite_token_valido() -> None:
    users = _UsersAuth()
    users.registrar("ana", "s3cretaA1")
    tok = await service.login_operador(users, "ana", "FIRMA", "ana", "s3cretaA1")
    assert isinstance(tok, str) and tok
    # El token validado devuelve al operador.
    assert await service.operador_de_token(tok, "ana", "FIRMA", users) == "ana"


async def test_login_operador_normaliza_el_usuario() -> None:
    users = _UsersAuth()
    users.registrar("ana", "passw0rd")
    # admin_user con mayúsculas/espacios y login en minúsculas: misma cuenta.
    tok = await service.login_operador(users, "  Ana ", "K", "ana", "passw0rd")
    assert tok is not None
    assert await service.operador_de_token(tok, "ANA", "K", users) == "ana"


async def test_login_operador_rechaza_password_mala() -> None:
    users = _UsersAuth()
    users.registrar("ana", "buenapwd")
    assert await service.login_operador(users, "ana", "K", "ana", "malapwd1") is None


async def test_login_operador_rechaza_a_quien_no_es_el_operador() -> None:
    users = _UsersAuth()
    users.registrar("ana", "passw0rd")
    users.registrar("bob", "passw0rd")
    # bob existe y la pass es correcta, pero el operador es ana: None.
    assert await service.login_operador(users, "ana", "K", "bob", "passw0rd") is None


async def test_login_operador_cerrado_si_no_configurado() -> None:
    users = _UsersAuth()
    users.registrar("ana", "passw0rd")
    assert await service.login_operador(users, "", "K", "ana", "passw0rd") is None
    assert await service.login_operador(users, "ana", "", "ana", "passw0rd") is None


async def test_operador_de_token_rechaza_falsos_y_no_configurado() -> None:
    users = _UsersAuth()
    users.registrar("ana", "passw0rd")
    crear_token = __import__(
        "orux.identity.tokens", fromlist=["crear_token"]
    ).crear_token
    tok = crear_token("ana", "FIRMA", ttl_seg=3600, epoch=0)
    assert await service.operador_de_token(tok, "ana", "FIRMA", users) == "ana"
    # Firma con otro secreto -> None (no lo emitió este server).
    assert await service.operador_de_token(tok, "ana", "OTRO", users) is None
    # Token válido pero el usuario NO es el operador -> None.
    users.registrar("bob", "passw0rd")
    assert await service.operador_de_token(tok, "bob", "FIRMA", users) is None
    # Basura / no configurado -> None (nunca explota).
    assert await service.operador_de_token("no.es-un-token", "ana", "FIRMA", users) is None
    assert await service.operador_de_token(tok, "", "FIRMA", users) is None
    assert await service.operador_de_token(tok, "ana", "", users) is None


async def test_operador_de_token_rechaza_tokens_con_epoch_revocado() -> None:
    """AUDITORIA-SEGURIDAD 2026-05-25 A-AUTH-01: tras revocar sesiones del
    operador, los tokens emitidos antes deben dejar de valer aunque su `exp`
    no haya pasado."""
    users = _UsersAuth()
    users.registrar("ana", "passw0rd")
    tok = await service.login_operador(users, "ana", "FIRMA", "ana", "passw0rd")
    assert tok is not None
    # Vivo antes de revocar.
    assert await service.operador_de_token(tok, "ana", "FIRMA", users) == "ana"
    # Revocar incrementa el epoch del usuario; el token viejo deja de valer.
    users.revocar_sesiones("ana")
    assert await service.operador_de_token(tok, "ana", "FIRMA", users) is None
