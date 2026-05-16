"""Capa 15 (paso 1, núcleo): dominio de equipos / membresía / invitaciones.

Pieza pura, sin red ni DB. Lo crítico a fijar como contrato:
- crear un equipo te hace su admin;
- sin equipo no "ves" nada (equipos_de vacío);
- solo el admin invita; el código es de un solo uso;
- dos equipos están aislados (uno no aparece en lo del otro).
"""

import pytest

from laidea.teams import MemTeamStore, TeamError


def test_crear_equipo_hace_admin_al_creador() -> None:
    s = MemTeamStore()
    t = s.crear_equipo("Equipo A", "Ana")
    assert set(t) == {"id", "nombre"} and t["nombre"] == "Equipo A"
    assert s.rol(t["id"], "ana") == "admin"
    assert s.es_miembro(t["id"], "ANA") is True  # normaliza


def test_nombre_vacio_falla() -> None:
    s = MemTeamStore()
    with pytest.raises(TeamError):
        s.crear_equipo("   ", "ana")


def test_sin_equipo_no_ve_nada() -> None:
    s = MemTeamStore()
    assert s.equipos_de("nadie") == []
    s.crear_equipo("A", "ana")
    assert s.equipos_de("beto") == []  # beto no fue invitado: no ve A


def test_invitar_solo_admin_y_codigo_un_solo_uso() -> None:
    s = MemTeamStore()
    t = s.crear_equipo("A", "ana")
    tid = t["id"]
    # Un no-miembro no puede invitar.
    with pytest.raises(TeamError):
        s.crear_invitacion(tid, "beto")
    code = s.crear_invitacion(tid, "ana")
    # Beto redime: entra como member.
    r = s.redimir(code, "beto")
    assert r == {"id": tid, "nombre": "A"}
    assert s.rol(tid, "beto") == "member"
    # Un member tampoco puede invitar (no es admin).
    with pytest.raises(TeamError):
        s.crear_invitacion(tid, "beto")
    # El código ya se usó: nadie más entra con él.
    assert s.redimir(code, "caro") is None
    assert s.es_miembro(tid, "caro") is False


def test_redimir_codigo_invalido() -> None:
    s = MemTeamStore()
    assert s.redimir("no-existe", "ana") is None


def test_redimir_idempotente_si_ya_es_miembro() -> None:
    s = MemTeamStore()
    t = s.crear_equipo("A", "ana")
    code = s.crear_invitacion(t["id"], "ana")
    # Ana ya es admin del equipo; redimir no la degrada a member.
    s.redimir(code, "ana")
    assert s.rol(t["id"], "ana") == "admin"


def test_equipos_de_y_miembros() -> None:
    s = MemTeamStore()
    a = s.crear_equipo("Alpha", "ana")
    b = s.crear_equipo("Beta", "ana")
    code = s.crear_invitacion(a["id"], "ana")
    s.redimir(code, "beto")
    # Ana está en los dos (admin); Beto solo en Alpha (member).
    assert [e["nombre"] for e in s.equipos_de("ana")] == ["Alpha", "Beta"]
    assert s.equipos_de("beto") == [
        {"id": a["id"], "nombre": "Alpha", "rol": "member"}
    ]
    assert s.miembros(a["id"]) == [
        {"usuario": "ana", "rol": "admin"},
        {"usuario": "beto", "rol": "member"},
    ]


def test_aislamiento_entre_equipos() -> None:
    # Dos equipos que no se enteran del otro: lo que pidió el usuario.
    s = MemTeamStore()
    eq1 = s.crear_equipo("Uno", "ana")
    eq2 = s.crear_equipo("Dos", "beto")
    assert s.es_miembro(eq1["id"], "beto") is False
    assert s.es_miembro(eq2["id"], "ana") is False
    assert [e["id"] for e in s.equipos_de("ana")] == [eq1["id"]]
    assert [e["id"] for e in s.equipos_de("beto")] == [eq2["id"]]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
