"""Tests del modelo de Workspace.

Workspace es donde vive el estado del servidor. Estos tests verifican el
comportamiento sin involucrar redes ni sockets — son los más simples y rápidos
de toda la suite. Si la lógica del estado se rompe, queremos que se rompa aquí
primero, no en los tests de integración (que son más lentos y dan menos pistas
sobre la causa).
"""

from laidea.state import Workspace


def test_workspace_empezando_vacio() -> None:
    ws = Workspace()
    assert ws.snapshot() == {}


def test_update_crea_archivo_si_no_existe() -> None:
    # Decisión de diseño: no necesitamos un "CreateFile" aparte. El primer
    # update sobre un path nuevo lo crea. Esto mantiene el protocolo más simple.
    ws = Workspace()
    ws.update("nuevo.txt", "hola")
    assert ws.snapshot() == {"nuevo.txt": "hola"}


def test_update_sobrescribe_archivo_existente() -> None:
    # Last-write-wins. Es el comportamiento de la capa cero/uno y se va a
    # reemplazar cuando metamos CRDT, pero por ahora es el contrato.
    ws = Workspace()
    ws.update("a.txt", "primero")
    ws.update("a.txt", "segundo")
    assert ws.snapshot()["a.txt"] == "segundo"


def test_archivos_son_independientes() -> None:
    # El test load-bearing de la capa 1: editar un archivo NO debe afectar a otro.
    # Si este test falla, los archivos están compartiendo estado y el modelo
    # entero de "un workspace con múltiples documentos" está mal.
    ws = Workspace()
    ws.update("a.py", "contenido de a")
    ws.update("b.py", "contenido de b")
    snap = ws.snapshot()
    assert snap == {"a.py": "contenido de a", "b.py": "contenido de b"}


def test_delete_quita_de_memoria() -> None:
    ws = Workspace()
    ws.update("a.py", "uno")
    ws.update("b.py", "dos")
    assert ws.delete("a.py") is True
    assert ws.snapshot() == {"b.py": "dos"}
    assert ws.delete("a.py") is False  # ya no existe -> no-op
