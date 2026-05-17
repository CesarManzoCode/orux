"""Capa 15: dominio de equipos / membresía / invitaciones.

Pieza pura, sin red ni DB (MemTeamStore). Interfaz async (misma superficie
que el adaptador Postgres). Lo crítico a fijar como contrato:
- crear un equipo te hace su admin;
- sin equipo no "ves" nada (equipos_de vacío);
- solo el admin invita; el código es de un solo uso;
- dos equipos están aislados (uno no aparece en lo del otro).
"""

import pytest

from laidea.teams import MemTeamStore, TeamError


async def test_crear_equipo_hace_admin_al_creador() -> None:
    s = MemTeamStore()
    t = await s.crear_equipo("Equipo A", "Ana")
    assert set(t) == {"id", "nombre"} and t["nombre"] == "Equipo A"
    assert await s.rol(t["id"], "ana") == "admin"
    assert await s.es_miembro(t["id"], "ANA") is True  # normaliza


async def test_nombre_vacio_falla() -> None:
    s = MemTeamStore()
    with pytest.raises(TeamError):
        await s.crear_equipo("   ", "ana")


async def test_sin_equipo_no_ve_nada() -> None:
    s = MemTeamStore()
    assert await s.equipos_de("nadie") == []
    await s.crear_equipo("A", "ana")
    assert await s.equipos_de("beto") == []  # beto no fue invitado: no ve A


async def test_invitar_solo_admin_y_codigo_un_solo_uso() -> None:
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")
    tid = t["id"]
    with pytest.raises(TeamError):
        await s.crear_invitacion(tid, "beto")  # no-miembro no invita
    code = await s.crear_invitacion(tid, "ana")
    r = await s.redimir(code, "beto")
    assert r == {"id": tid, "nombre": "A"}
    assert await s.rol(tid, "beto") == "member"
    with pytest.raises(TeamError):
        await s.crear_invitacion(tid, "beto")  # member tampoco invita
    assert await s.redimir(code, "caro") is None  # código ya usado
    assert await s.es_miembro(tid, "caro") is False


async def test_redimir_codigo_invalido() -> None:
    s = MemTeamStore()
    assert await s.redimir("no-existe", "ana") is None


async def test_redimir_idempotente_si_ya_es_miembro() -> None:
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")
    code = await s.crear_invitacion(t["id"], "ana")
    await s.redimir(code, "ana")  # ya es admin: no la degrada a member
    assert await s.rol(t["id"], "ana") == "admin"


async def test_equipos_de_y_miembros() -> None:
    s = MemTeamStore()
    a = await s.crear_equipo("Alpha", "ana")
    await s.crear_equipo("Beta", "ana")
    code = await s.crear_invitacion(a["id"], "ana")
    await s.redimir(code, "beto")
    assert [e["nombre"] for e in await s.equipos_de("ana")] == ["Alpha", "Beta"]
    assert await s.equipos_de("beto") == [
        {"id": a["id"], "nombre": "Alpha", "rol": "member"}
    ]
    assert await s.miembros(a["id"]) == [
        {"usuario": "ana", "rol": "admin"},
        {"usuario": "beto", "rol": "member"},
    ]


async def test_aislamiento_entre_equipos() -> None:
    # Dos equipos que no se enteran del otro: lo que pidió el usuario.
    s = MemTeamStore()
    eq1 = await s.crear_equipo("Uno", "ana")
    eq2 = await s.crear_equipo("Dos", "beto")
    assert await s.es_miembro(eq1["id"], "beto") is False
    assert await s.es_miembro(eq2["id"], "ana") is False
    assert [e["id"] for e in await s.equipos_de("ana")] == [eq1["id"]]
    assert [e["id"] for e in await s.equipos_de("beto")] == [eq2["id"]]


async def test_plan_por_defecto_es_free() -> None:
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")
    assert await s.plan(t["id"]) == "free"
    assert (await s.equipo(t["id"]))["plan"] == "free"
    assert await s.plan("no-existe") == "free"  # lado seguro


async def test_tope_de_devs_free_y_premium() -> None:
    # Capa 22: free = 5 devs. El creador ya es 1; entran 4 (=5), el 6º
    # se rechaza con mensaje de plan SIN quemar el código.
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")  # ana = miembro 1 (admin)
    tid = t["id"]
    for i in range(4):  # llega a 5 miembros
        code = await s.crear_invitacion(tid, "ana")
        assert await s.redimir(code, f"dev{i}") is not None
    assert len(await s.miembros(tid)) == 5
    code6 = await s.crear_invitacion(tid, "ana")
    with pytest.raises(TeamError, match="premium"):
        await s.redimir(code6, "dev5")
    # Idempotente: un ya-miembro no cuenta de nuevo aunque esté "lleno".
    code_ana = await s.crear_invitacion(tid, "ana")
    assert await s.redimir(code_ana, "ana") is not None
    # Upgrade: el código RECHAZADO antes NO se quemó y ahora sí entra.
    await s.set_plan(tid, "premium")
    assert await s.redimir(code6, "dev5") is not None
