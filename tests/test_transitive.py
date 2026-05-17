"""Capa 24: impacto transitivo (puro, sandbox). Lo que se prueba es la
DECISIÓN de diseño: propaga por interfaz contaminada, NO por referencias
de referencias. Uso en cuerpo = terminal; uso en interfaz = se propaga.
Ciclos, profundidad y presupuesto acotan sin colgar ni mentir."""

from __future__ import annotations

from laidea.analysis.modelo import Simbolo
from laidea.analysis.transitive import impacto_transitivo


def _sim(nombre, fuente, firma="", superficie=()):
    return Simbolo(nombre=nombre, tipo="?", fuente=fuente, firma=firma,
                   superficie=frozenset(superficie), detallado=True)


def _todo_py(_p):  # un solo lenguaje en estos tests
    return "py"


def test_propaga_por_interfaz_y_corta_en_cuerpo() -> None:
    ws = {
        "models.py": "class Usuario: ...",
        "factory.py": "def make_user() -> Usuario: ...",   # interfaz
        "api.py": "def handler(): make_user()",              # cuerpo
        "report.py": "def r(): Usuario()",                   # cuerpo directo
    }
    simbolos = {
        "factory.py": {"make_user": _sim("make_user",
                       "def make_user() -> Usuario: ...",
                       firma="() -> Usuario")},
        "api.py": {"handler": _sim("handler",
                   "def handler(): make_user()", firma="()")},
        "report.py": {"r": _sim("r", "def r(): Usuario()", firma="()")},
    }
    fan = {
        ("Usuario", "models.py"): {"factory.py", "report.py"},
        ("make_user", "factory.py"): {"api.py"},
    }
    out, trunc = impacto_transitivo(
        ws, "models.py", ["Usuario"],
        fan_out=lambda s, o: fan.get((s, o), set()),
        extraer=lambda c: next(
            (v for f, v in simbolos.items() if ws.get(f) == c), {}
        ),
        lenguaje_de=_todo_py,
    )
    assert trunc is False
    # factory.make_user: Usuario en su firma => interfaz => propaga.
    assert out["factory.py"][0]["sym"] == "make_user"
    assert out["factory.py"][0]["terminal"] is False
    assert "interfaz" in out["factory.py"][0]["motivo"]
    # report.r: Usuario solo en cuerpo => terminal.
    assert out["report.py"][0]["terminal"] is True
    # api.handler: alcanzado transitivamente vía make_user, uso en cuerpo
    # => terminal; la cadena muestra los 3 hops.
    assert out["api.py"][0]["terminal"] is True
    assert out["api.py"][0]["cadena"] == [
        "models.py:Usuario", "factory.py:make_user", "api.py:handler"
    ]


def test_ciclo_no_cuelga() -> None:
    ws = {"a.py": "A", "b.py": "B"}
    sa = {"a.py": {"A": _sim("A", "A B", firma="B")},
          "b.py": {"B": _sim("B", "B A", firma="A")}}
    fan = {("A", "a.py"): {"b.py"}, ("B", "b.py"): {"a.py"},
           ("A", "b.py"): {"a.py"}, ("B", "a.py"): {"b.py"}}
    out, trunc = impacto_transitivo(
        ws, "a.py", ["A"],
        fan_out=lambda s, o: fan.get((s, o), set()),
        extraer=lambda c: sa["a.py"] if c == "A" else sa["b.py"],
        lenguaje_de=_todo_py,
    )
    assert isinstance(out, dict)  # terminó (visitados cortó el ciclo)


def test_limite_de_profundidad_trunca_honesto() -> None:
    # Cadena que SÍ propaga (cada símbolo expone el anterior en su firma):
    # A(a.py) -> B usa A en firma -> C usa B en firma -> ...
    ws = {"a.py": "ca", "b.py": "cb", "c.py": "cc", "d.py": "cd"}
    syms = {
        "ca": {},  # a.py: el origen
        "cb": {"B": _sim("B", "B usa A", firma="A")},
        "cc": {"C": _sim("C", "C usa B", firma="B")},
        "cd": {"D": _sim("D", "D usa C", firma="C")},
    }
    fan = {("A", "a.py"): {"b.py"}, ("B", "b.py"): {"c.py"},
           ("C", "c.py"): {"d.py"}}
    out, trunc = impacto_transitivo(
        ws, "a.py", ["A"],
        fan_out=lambda s, o: fan.get((s, o), set()),
        extraer=lambda c: syms.get(c, {}),
        lenguaje_de=_todo_py, max_prof=2,
    )
    # Llega a B (prof1) y C (prof2); en C, propagar sería prof>=max_prof
    # => truncado honesto, no se sigue a D.
    assert trunc is True
    assert "b.py" in out and "c.py" in out
    assert "d.py" not in out


def test_presupuesto_de_nodos_trunca() -> None:
    ws = {"m.py": "S"} | {f"u{i}.py": "u" for i in range(10)}
    syms = {"m.py": {}} | {
        f"u{i}.py": {f"f{i}": _sim(f"f{i}", "S", firma="")}
        for i in range(10)
    }
    out, trunc = impacto_transitivo(
        ws, "m.py", ["S"],
        fan_out=lambda s, o: {f"u{i}.py" for i in range(10)}
        if o == "m.py" else set(),
        extraer=lambda c: next(
            (v for f, v in syms.items() if ws.get(f) == c), {}
        ),
        lenguaje_de=_todo_py, max_nodos=3,
    )
    assert trunc is True
    assert sum(len(v) for v in out.values()) <= 3


def test_no_cruza_lenguajes() -> None:
    ws = {"m.py": "S", "x.ts": "S"}
    out, trunc = impacto_transitivo(
        ws, "m.py", ["S"],
        fan_out=lambda s, o: {"x.ts"},
        extraer=lambda c: {"f": _sim("f", "S", firma="S")},
        lenguaje_de=lambda p: "py" if p.endswith(".py") else "ts",
    )
    assert out == {} and trunc is False  # .ts no se cruza desde .py
