"""Tests del Roster, en particular la identidad estable por token.

La presencia (path/línea) ya se prueba end-to-end en test_sync.py. Aquí
fijamos a nivel unidad la pieza nueva: el token hace que reconectar devuelva
la MISMA identidad (de eso depende que recargar la página no borre el
ownership), mientras la presencia sí es efímera.
"""

from laidea.state import Roster


def test_sin_token_identidad_nueva_cada_vez() -> None:
    r = Roster()
    a = r.asignar()
    b = r.asignar()
    assert a.client_id != b.client_id


def test_mismo_token_reusa_identidad() -> None:
    r = Roster()
    a = r.asignar(token="tok-1")
    # "Se desconecta": la presencia se borra...
    r.quitar(a.client_id)
    # ...pero al volver con el mismo token, misma identidad completa.
    a2 = r.asignar(token="tok-1")
    assert a2.client_id == a.client_id
    assert a2.name == a.name
    assert a2.color == a.color


def test_tokens_distintos_identidades_distintas() -> None:
    r = Roster()
    a = r.asignar(token="tok-a")
    b = r.asignar(token="tok-b")
    assert a.client_id != b.client_id


def test_reconectar_resetea_la_presencia_no_la_identidad() -> None:
    # Volver con el mismo token NO te devuelve a donde estabas: la presencia
    # (path/línea) nace limpia, solo la identidad persiste.
    r = Roster()
    a = r.asignar(token="t")
    r.mover(a.client_id, "main.py", 12)
    assert r.lineas_ocupadas("main.py", excepto="otro") == {12}
    r.quitar(a.client_id)
    a2 = r.asignar(token="t")
    assert a2.client_id == a.client_id
    assert a2.path is None  # presencia reseteada
    assert r.lineas_ocupadas("main.py", excepto="otro") == set()
