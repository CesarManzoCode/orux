"""Tests del Roster. Capa 7: la identidad ES el usuario, determinista.

La presencia (path/línea) ya se prueba end-to-end en test_sync.py. Aquí
fijamos a nivel unidad que la identidad se deriva del usuario (mismo usuario
-> misma identidad completa, sin guardar nada), mientras la presencia sí es
efímera (reconectar no te devuelve a donde estabas).
"""

from laidea.state import Roster
from laidea.state.presence import color_de


def test_usuarios_distintos_identidades_distintas() -> None:
    r = Roster()
    a = r.asignar("ana")
    b = r.asignar("beto")
    assert a.client_id == "ana"
    assert b.client_id == "beto"
    assert a.client_id != b.client_id


def test_mismo_usuario_misma_identidad_completa() -> None:
    r = Roster()
    a = r.asignar("ana")
    r.quitar(a.client_id)  # "se desconecta": la presencia se borra...
    a2 = r.asignar("ana")  # ...pero volver como ana da la MISMA identidad.
    assert a2.client_id == a.client_id == "ana"
    assert a2.name == a.name == "ana"
    assert a2.color == a.color


def test_color_es_determinista_y_estable() -> None:
    # Mismo usuario => mismo color siempre, sin estado (otro Roster igual).
    assert color_de("ana") == color_de("ana")
    assert Roster().asignar("ana").color == color_de("ana")


def test_reconectar_resetea_la_presencia_no_la_identidad() -> None:
    r = Roster()
    a = r.asignar("ana")
    r.mover(a.client_id, "main.py", 12)
    assert r.lineas_ocupadas("main.py", excepto="otro") == {12}
    r.quitar(a.client_id)
    a2 = r.asignar("ana")
    assert a2.client_id == a.client_id  # identidad persiste
    assert a2.path is None  # presencia reseteada
    assert r.lineas_ocupadas("main.py", excepto="otro") == set()
