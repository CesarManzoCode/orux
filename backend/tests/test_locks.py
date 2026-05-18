"""Tests de la prevención de colisiones (capa 5).

`lineas_tocadas` es pura y se prueba sin red. Lo crítico es la propiedad que
hace que el lock no sea molesto: insertar una línea NO marca como tocadas las
que solo se desplazaron. Sin esa propiedad bloquearíamos a gente que ni fue
rozada y la capa sería inusable.

`Roster.lineas_ocupadas` traduce presencia (capa 2) a "qué líneas están
reservadas", que es la otra mitad del lock.
"""

from orux.state import Roster, lineas_tocadas


def test_sin_cambios_no_toca_nada() -> None:
    assert lineas_tocadas("a\nb\nc", "a\nb\nc") == set()


def test_modificar_una_linea_la_toca() -> None:
    # Cambia solo la línea 2.
    assert lineas_tocadas("a\nb\nc", "a\nB\nc") == {2}


def test_borrar_una_linea_la_toca() -> None:
    assert lineas_tocadas("a\nb\nc", "a\nc") == {2}


def test_insertar_arriba_no_toca_las_de_abajo() -> None:
    # LA propiedad clave: meter una línea al principio NO toca a\nb\nc, solo
    # agrega. Con comparación posicional ingenua todas saldrían "cambiadas".
    assert lineas_tocadas("a\nb\nc", "NUEVA\na\nb\nc") == set()


def test_insertar_en_medio_no_toca_las_existentes() -> None:
    assert lineas_tocadas("a\nb\nc", "a\nb\nNUEVA\nc") == set()


def test_archivo_vacio_a_contenido_toca_la_primera() -> None:
    # "" se parte como [""]; pasar a "hola" reemplaza esa línea 1.
    assert lineas_tocadas("", "hola") == {1}


def test_cambiar_la_ultima_linea() -> None:
    assert lineas_tocadas("a\nb\nc", "a\nb\nZ") == {3}


def test_roster_lineas_ocupadas_excluye_al_propio_y_otros_paths() -> None:
    r = Roster()
    a = r.asignar("ana")
    b = r.asignar("beto")
    c = r.asignar("caro")
    r.mover(a.client_id, "main.py", 10)
    r.mover(b.client_id, "main.py", 4)
    r.mover(c.client_id, "otro.py", 4)
    # Para 'a': en main.py están ocupadas las líneas de OTROS (b -> 4). La suya
    # (10) no cuenta (no te bloqueas a ti mismo). c está en otro archivo.
    assert r.lineas_ocupadas("main.py", excepto=a.client_id) == {4}
    # Para 'b': la línea de a (10).
    assert r.lineas_ocupadas("main.py", excepto=b.client_id) == {10}
    # Nadie en un archivo sin presencia.
    assert r.lineas_ocupadas("vacio.py", excepto=a.client_id) == set()


# --- Blindaje: tope anti-DoS de la matriz LCS (robustez, capa de seguridad) -

def test_archivo_gigante_no_revienta_y_es_conservador() -> None:
    """Un update con un archivo enorme NO debe construir la matriz O(n·m)
    (congelaría el event loop de TODOS los equipos). Se degrada a la
    comparación posicional: rápida y CONSERVADORA (nunca reporta de menos,
    así la capa 5 sigue protegiendo)."""
    from orux.state.locks import _LCS_MAX_CELDAS

    n = int(_LCS_MAX_CELDAS**0.5) + 50  # n·n por encima del tope -> fallback
    viejo = "\n".join(f"linea {i}" for i in range(n))
    # Cambia SOLO la línea 0; el resto idéntico y en su misma posición.
    nuevo = "\n".join(
        ("CAMBIADA" if i == 0 else f"linea {i}") for i in range(n)
    )
    tocadas = lineas_tocadas(viejo, nuevo)
    # La 1 está tocada; ninguna línea intacta en su posición se reporta.
    assert 1 in tocadas
    assert tocadas == {1}


def test_fallback_nunca_subreporta_una_linea_borrada() -> None:
    """Propiedad de seguridad del fallback: una línea vieja que desaparece
    SIEMPRE cuenta como tocada (sub-reportar dejaría pasar una colisión)."""
    from orux.state.locks import _tocadas_posicional

    a = ["a", "b", "c", "d"]
    b = ["a", "X"]  # b, c, d ya no están / cambiaron
    assert _tocadas_posicional(a, b) == {2, 3, 4}
