"""Tests de la persistencia en disco (capa 3).

Usan `tmp_path` (el directorio temporal que pytest crea fresco por test) como
raíz del storage. Así cada test escribe en su propia carpeta aislada y nada
sobrevive entre tests: el mismo principio que el `server_port` de los tests de
integración, aplicado al disco.

Lo crítico aquí, además del roundtrip básico, es la seguridad: el `path` viene
del cliente por la red, y un path que se escapa del directorio raíz tiene que
ser rechazado, no escrito.
"""

import pytest

from laidea.state import DiskStorage, Workspace


def test_guardar_y_cargar_roundtrip(tmp_path) -> None:
    s = DiskStorage(tmp_path)
    s.guardar("main.py", "print('hola')")
    assert s.cargar() == {"main.py": "print('hola')"}


def test_cargar_directorio_inexistente_es_vacio(tmp_path) -> None:
    # Primer arranque limpio: el directorio aún no existe. No es error.
    s = DiskStorage(tmp_path / "todavia-no-existe")
    assert s.cargar() == {}


def test_paths_anidados_crean_subcarpetas(tmp_path) -> None:
    # `src/auth.py` debe crear la carpeta `src/` real y volver con la clave
    # en formato POSIX (con `/`), que es como viaja por el protocolo.
    s = DiskStorage(tmp_path)
    s.guardar("src/auth.py", "def login(): pass")
    assert (tmp_path / "src" / "auth.py").is_file()
    assert s.cargar() == {"src/auth.py": "def login(): pass"}


def test_sobrescribe_last_write_wins(tmp_path) -> None:
    s = DiskStorage(tmp_path)
    s.guardar("a.txt", "primero")
    s.guardar("a.txt", "segundo")
    assert s.cargar()["a.txt"] == "segundo"


@pytest.mark.parametrize(
    "malicioso",
    ["../fuera.txt", "../../etc/passwd", "/etc/passwd", "a/../../b.txt", "", "."],
)
def test_rechaza_paths_que_se_escapan(tmp_path, malicioso: str) -> None:
    # El path lo manda el cliente: no es de confiar. Cualquier intento de
    # escribir fuera del directorio raíz se rechaza con ValueError y NO toca
    # el disco.
    s = DiskStorage(tmp_path)
    with pytest.raises(ValueError):
        s.guardar(malicioso, "no deberia escribirse")
    # Nada se creó fuera de la raíz.
    assert list(tmp_path.iterdir()) == []


# --- Integración Workspace <-> storage ---


def test_workspace_sin_storage_sigue_en_memoria(tmp_path) -> None:
    # Contrato de capas 1/2 intacto: sin storage, nada toca el disco.
    ws = Workspace()
    ws.update("x.py", "y = 1")
    assert ws.snapshot() == {"x.py": "y = 1"}
    assert list(tmp_path.iterdir()) == []


def test_workspace_con_storage_persiste_en_update(tmp_path) -> None:
    s = DiskStorage(tmp_path)
    ws = Workspace(storage=s)
    ws.update("notas.md", "# título")
    # Un storage nuevo, montado sobre la misma carpeta, ve lo que se escribió:
    # prueba que de verdad llegó a disco, no solo a memoria.
    assert DiskStorage(tmp_path).cargar() == {"notas.md": "# título"}


def test_workspace_se_hidrata_de_disco(tmp_path) -> None:
    # Simula "el server se reinició": dejamos archivos en disco y un Workspace
    # nuevo debe reconstruir su estado desde ahí.
    DiskStorage(tmp_path).guardar("main.py", "x = 1")
    ws = Workspace(storage=DiskStorage(tmp_path))
    ws.cargar_de_disco()
    assert ws.snapshot() == {"main.py": "x = 1"}


def test_path_inseguro_no_tumba_el_workspace(tmp_path, caplog) -> None:
    # Si un cliente manda un path que el storage rechaza, la memoria debe
    # quedar coherente igual y el tiempo real seguir vivo: persistir nunca
    # puede propagar una excepción que mate la conexión.
    ws = Workspace(storage=DiskStorage(tmp_path))
    ws.update("../escape.txt", "intento")
    assert ws.snapshot() == {"../escape.txt": "intento"}  # memoria intacta
    assert not (tmp_path.parent / "escape.txt").exists()  # disco protegido


def test_reinicio_completo_conserva_el_workspace(tmp_path) -> None:
    # El test que justifica toda la capa: editar, "apagar" (descartar el
    # Workspace) y "encender" otro sobre la misma carpeta conserva el estado.
    s = DiskStorage(tmp_path)
    ws1 = Workspace(storage=s)
    ws1.update("a.py", "contenido a")
    ws1.update("dir/b.py", "contenido b")

    ws2 = Workspace(storage=DiskStorage(tmp_path))
    ws2.cargar_de_disco()
    assert ws2.snapshot() == {"a.py": "contenido a", "dir/b.py": "contenido b"}


def test_cargar_ignora_el_directorio_git(tmp_path) -> None:
    # Capa 8: el workspace puede ser un repo git. `.git/` NO son archivos del
    # proyecto: no deben entrar al workspace ni re-persistirse.
    s = DiskStorage(tmp_path)
    s.guardar("main.py", "x = 1")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (tmp_path / ".git" / "refs").mkdir()
    (tmp_path / ".git" / "refs" / "head").write_text("abc\n", encoding="utf-8")
    assert s.cargar() == {"main.py": "x = 1"}
