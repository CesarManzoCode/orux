"""Capa 12 (núcleo): admin del workspace + asignación de ownership.

El bloqueo real para soltárselo a un equipo open source ya hecho era que
nadie con autoridad podía repartir las zonas: el ownership se auto-reclamaba
por quien tocaba primero, lo cual en un proyecto existente no organiza nada.
Capa 12 introduce un admin (mínimo: el primer registrado) que reasigna desde
un panel. Acá se prueba SOLO el núcleo puro; el server y el panel son 12.2/12.3.
"""

from __future__ import annotations

import pytest

from laidea.identity.store import UserStore
from laidea.state.ownership import Ownership


# --- UserStore.admin(): el primero registrado, sin tocar el schema ---

def test_admin_es_el_primer_registrado(tmp_path):
    s = UserStore(tmp_path / "users.json")
    assert s.admin() is None  # nadie todavía
    s.registrar("Ana", "clave-ana")
    s.registrar("Beto", "clave-beto")
    s.registrar("Caro", "clave-caro")
    # El primero gana, aunque después se registren más.
    assert s.admin() == "ana"


def test_admin_sobrevive_a_reiniciar_sin_migracion(tmp_path):
    ruta = tmp_path / "users.json"
    s1 = UserStore(ruta)
    s1.registrar("Lider", "x")
    s1.registrar("Otro", "y")
    # Otro proceso/arranque lee el MISMO json (orden de inserción preservado
    # por json/dict): el admin es estable sin ningún campo nuevo en disco.
    s2 = UserStore(ruta)
    assert s2.admin() == "lider"


def test_usuarios_lista_estable_sin_filtrar_password(tmp_path):
    s = UserStore(tmp_path / "users.json")
    s.registrar("Zoe", "p1")
    s.registrar("Ana", "p2")
    listado = s.usuarios()
    assert listado == ["ana", "zoe"]  # ordenado, normalizado
    # Es solo nombres: ningún registro de contraseña se filtra por aquí.
    assert all(isinstance(u, str) and ":" not in u for u in listado)


# --- Ownership.asignar(): el admin SÍ reasigna (claim no robaba) ---

def test_asignar_pone_dueno_donde_no_habia():
    o = Ownership()
    assert o.owner("src/auth.py") is None
    o.asignar("src/auth.py", "ana")
    assert o.owner("src/auth.py") == "ana"


def test_asignar_reasigna_aunque_ya_tenga_dueno():
    """La diferencia con claim: el admin puede mover una zona ya dueña.

    claim respeta al dueño actual (coordinación, no robo). El admin reparte
    el proyecto: si la clase quedó mal asignada, la mueve.
    """
    o = Ownership()
    assert o.claim("models.py", "ana") is True
    # claim de otro NO roba (contrato de capa 4, lo dejamos firme):
    assert o.claim("models.py", "beto") is False
    assert o.owner("models.py") == "ana"
    # asignar (admin) SÍ reasigna:
    o.asignar("models.py", "beto")
    assert o.owner("models.py") == "beto"


def test_asignar_persiste(tmp_path):
    ruta = tmp_path / "ownership.json"
    o1 = Ownership(ruta)
    o1.asignar("core/api.ts", "caro")
    o2 = Ownership(ruta)
    assert o2.owner("core/api.ts") == "caro"


def test_admin_libera_con_la_pieza_que_ya_existia():
    """Revocar = `liberar` (ya existía para borrar archivo). El panel admin
    reusa eso para 'quitar dueño': no hace falta pieza nueva para revocar.
    """
    o = Ownership()
    o.asignar("x.py", "ana")
    assert o.liberar("x.py") is True
    assert o.owner("x.py") is None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
