"""Tests del núcleo de análisis semántico (capa 6, Python).

Pieza pura: sin red ni estado. Lo crítico a fijar como contrato:
- detecta cambios reales de símbolos top (no ruido por reformatear nada);
- mapea símbolo cambiado -> archivos que lo usan;
- NO explota ni opina cuando el código está a medio escribir (SyntaxError).
"""

from laidea.analysis import (
    definiciones_top,
    impacto,
    referencias,
    simbolos_cambiados,
)


def test_definiciones_top_solo_nivel_modulo() -> None:
    src = (
        "def foo():\n"
        "    def interna():\n"   # anidada: NO cuenta
        "        pass\n"
        "    return interna\n"
        "\n"
        "class Bar:\n"
        "    def metodo(self):\n"  # método: NO cuenta
        "        pass\n"
    )
    assert set(definiciones_top(src)) == {"foo", "Bar"}


def test_codigo_roto_no_explota() -> None:
    # Edición a medias: lo más normal en un editor en vivo.
    assert definiciones_top("def foo(:\n  pass") == {}
    assert referencias("import") == set()
    assert simbolos_cambiados("def f(): pass", "def f(:") == set()


def test_referencias_incluye_nombres_e_imports() -> None:
    src = "from mod import Usuario\nx = Usuario()\ny = otra_func()\n"
    refs = referencias(src)
    assert "Usuario" in refs
    assert "otra_func" in refs


def test_simbolos_cambiados_detecta_modificacion() -> None:
    viejo = "def f():\n    return 1\n"
    nuevo = "def f():\n    return 2\n"
    assert simbolos_cambiados(viejo, nuevo) == {"f"}


def test_simbolos_cambiados_ignora_lo_que_no_cambia() -> None:
    src = "def f():\n    return 1\n\ndef g():\n    return 2\n"
    # Cambiamos solo g; f no debe reportarse.
    nuevo = "def f():\n    return 1\n\ndef g():\n    return 3\n"
    assert simbolos_cambiados(src, nuevo) == {"g"}


def test_simbolos_cambiados_detecta_agregado_y_eliminado() -> None:
    assert simbolos_cambiados("def f(): pass", "def f(): pass\ndef g(): pass") == {"g"}
    assert simbolos_cambiados("def f(): pass\ndef g(): pass", "def f(): pass") == {"g"}


def test_simbolos_cambiados_vacio_si_nuevo_roto() -> None:
    # No opinamos sobre código que no parsea: cero falsos positivos.
    assert simbolos_cambiados("def f(): pass", "def f(: pass") == set()


def test_impacto_encuentra_quien_usa_el_simbolo() -> None:
    workspace = {
        "models.py": "class Usuario:\n    pass\n",
        "auth.py": "from models import Usuario\n\ndef login():\n    return Usuario()\n",
        "infra.py": "import os\n",  # no usa Usuario
        "notas.md": "Usuario",  # no es .py: se ignora
    }
    viejo = "class Usuario:\n    pass\n"
    nuevo = "class Usuario:\n    def __init__(self):\n        self.activo = True\n"
    res = impacto(workspace, "models.py", viejo, nuevo)
    assert res == {"Usuario": ["auth.py"]}


def test_impacto_vacio_si_nadie_usa_el_simbolo() -> None:
    workspace = {
        "a.py": "def solitaria():\n    return 1\n",
        "b.py": "x = 1\n",
    }
    res = impacto(workspace, "a.py", "def solitaria():\n    return 1\n",
                  "def solitaria():\n    return 2\n")
    assert res == {}


def test_impacto_solo_para_archivos_py() -> None:
    workspace = {"notas.md": "texto", "a.py": "x = 1"}
    assert impacto(workspace, "notas.md", "viejo", "nuevo") == {}
