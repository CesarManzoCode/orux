"""Capa 23: la capa de servicio de la API de operador (pura, sandbox).

Sin HTTP ni Postgres: MemTeamStore + un store de usuarios async mínimo.
Fija el comportamiento que la cáscara starlette solo traduce a HTTP (la
cáscara se verifica en VPS, igual que pyright/asyncpg)."""

from __future__ import annotations

import pytest

from laidea.api import service
from laidea.teams import MemTeamStore


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
