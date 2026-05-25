"""Capa 15: dominio de equipos / membresía / invitaciones.

Pieza pura, sin red ni DB (MemTeamStore). Interfaz async (misma superficie
que el adaptador Postgres). Lo crítico a fijar como contrato:
- crear un equipo te hace su admin;
- sin equipo no "ves" nada (equipos_de vacío);
- solo el admin invita; el código es de un solo uso;
- dos equipos están aislados (uno no aparece en lo del otro).
"""

from datetime import datetime, timedelta, timezone

import pytest

from orux.teams import MemTeamStore, TeamError


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


@pytest.mark.parametrize(
    "malo",
    [
        None,                              # tipo inválido
        "",                                # vacío puro
        "  ",                              # solo espacios
        "a" * 41,                          # exceso (>40)
        "Equipo <script>alert(1)</script>", # HTML/XSS dressed
        "Equipo>algo",                     # otros HTML chars
        "Equipo\x00malo",                  # NUL
        "Equipo\nlinea",                   # control char
        "Equipo\x7fDEL",                   # DEL
        "Equipo‮con-rtl",             # bidi RTL override (suplantación)
        "Equipo​zwsp",                # zero-width space
    ],
)
async def test_crear_equipo_rechaza_nombre_invalido(malo):
    s = MemTeamStore()
    with pytest.raises(TeamError):
        await s.crear_equipo(malo, "ana")


async def test_crear_equipo_normaliza_espacios() -> None:
    """Trim al borde + colapso de runs internos: tres equipos con espacios
    distintos en el medio NO son equipos distintos."""
    s = MemTeamStore()
    t = await s.crear_equipo("   Mi  Equipo   ", "ana")
    assert t["nombre"] == "Mi Equipo"


async def test_crear_equipo_acepta_unicode_y_puntuacion() -> None:
    # Acentos, emoji y puntuación normal son válidos: queremos "Equipo de
    # Ana", "Founders' Workspace", "ML/CV" etc.
    s = MemTeamStore()
    assert (await s.crear_equipo("Equipo de Ana", "ana"))["nombre"] == "Equipo de Ana"
    assert (await s.crear_equipo("Founders' WS", "beto"))["nombre"] == "Founders' WS"
    assert (await s.crear_equipo("ML/CV", "caro"))["nombre"] == "ML/CV"


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
    # `miembros` (capa 31, cobro por asiento): Alpha tiene a ana + beto.
    assert await s.equipos_de("beto") == [
        {"id": a["id"], "nombre": "Alpha", "rol": "member", "plan": "free",
         "miembros": 2}
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


# --- Capa 31: cobro por asiento ------------------------------------------


async def test_contar_miembros() -> None:
    # contar_miembros = asientos que se le cobran al equipo.
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")
    tid = t["id"]
    assert await s.contar_miembros(tid) == 1  # solo el creador
    code = await s.crear_invitacion(tid, "ana")
    await s.redimir(code, "beto")
    assert await s.contar_miembros(tid) == 2
    assert await s.contar_miembros("no-existe") == 0


# --- BACKEND-AUDIT-0214 (fix): caducidad real de invitaciones -----------
#
# El fix anterior dejó la columna `expires_at` pero ni `crear_invitacion`
# la seteaba ni `redimir` la verificaba: un código filtrado seguía vivo
# para siempre. Estos tests bloquean la regresión.


async def test_invitacion_se_crea_con_expires_at_en_el_futuro() -> None:
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")
    code = await s.crear_invitacion(t["id"], "ana")
    # No se expone API pública para leer expires_at (es detalle interno
    # del store); inspeccionamos el dict para fijar el contrato del fix.
    inv = s._invites[code]
    assert "expires_at" in inv
    assert inv["expires_at"] > datetime.now(timezone.utc)
    # Y no más allá de ~7d (defensa contra "se nos fue al infinito").
    assert inv["expires_at"] <= datetime.now(timezone.utc) + timedelta(days=8)


async def test_invitacion_vigente_se_redime_normal() -> None:
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")
    code = await s.crear_invitacion(t["id"], "ana")
    r = await s.redimir(code, "beto")
    assert r == {"id": t["id"], "nombre": "A"}


async def test_invitacion_expirada_levanta_team_error() -> None:
    """Caducó: TeamError con mensaje accionable (no None silencioso, que
    confundiría con 'código inexistente'). El lobby muestra el `str(e)`
    al invitado."""
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")
    code = await s.crear_invitacion(t["id"], "ana")
    # Forzamos expiración pisando el campo (el store es para tests/dev y
    # exponer un `_for_test_caducar` sería peor que tocar el dict).
    s._invites[code]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    with pytest.raises(TeamError, match="expir"):
        await s.redimir(code, "beto")
    # Y el code NO se consumió (sigue sin `usado_por`): si el admin emite
    # uno nuevo el viejo no quedó "quemado" por el intento.
    assert s._invites[code]["usado_por"] is None


async def test_invitacion_expirada_no_suma_miembro() -> None:
    """Defensa estructural: aunque alguien manipule el flujo, la cuenta
    NO se vuelve miembro del equipo a partir de una invitación expirada."""
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")
    code = await s.crear_invitacion(t["id"], "ana")
    s._invites[code]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    )
    with pytest.raises(TeamError):
        await s.redimir(code, "beto")
    assert await s.es_miembro(t["id"], "beto") is False


async def test_suscripcion_se_guarda_y_se_limpia() -> None:
    # actualizar_suscripcion fija plan + id de Stripe juntos (lo usa el
    # webhook). El equipo nuevo no tiene suscripción.
    s = MemTeamStore()
    t = await s.crear_equipo("A", "ana")
    tid = t["id"]
    assert await s.suscripcion(tid) == ""
    # Alta: premium + id de la suscripción.
    await s.actualizar_suscripcion(tid, "premium", "sub_abc")
    assert await s.plan(tid) == "premium"
    assert await s.suscripcion(tid) == "sub_abc"
    # Baja: vuelve a free y limpia el id (la suscripción ya no existe).
    await s.actualizar_suscripcion(tid, "free", "")
    assert await s.plan(tid) == "free"
    assert await s.suscripcion(tid) == ""
    # Equipo inexistente: no explota, sigue sin suscripción.
    await s.actualizar_suscripcion("nope", "premium", "sub_x")
    assert await s.suscripcion("nope") == ""
