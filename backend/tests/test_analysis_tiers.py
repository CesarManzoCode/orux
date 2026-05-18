"""Capa 16: la jerarquía de tiers reproduce EXACTO la lógica de capa 6/15.

Antes de rewirear el dispatcher, se prueba que el camino nuevo (modelo
normalizado + `tiers.cambios`) da byte-idéntico lo que daban las
implementaciones por lenguaje (`python.cambios_que_importan` /
`javascript.cambios_que_importan`). Es el mismo método que capa 15 3a-i:
extraer, probar no-regresión, recién después rewirear.
"""

from __future__ import annotations

import pytest

from orux.analysis import javascript, python, tiers
from orux.analysis.modelo import Simbolo, cambios_que_importan_modelo

# (viejo, nuevo) que ejercitan cada rama: eliminado, firma cambiada,
# construcción de clase, miembro público quitado, def↔class, cuerpo-solo
# (silencio), código roto, alta de símbolo.
CASOS_PY = [
    ("def f(a): pass", "def f(a, b): pass"),                 # firma
    ("def f(a): pass", "def g(a): pass"),                    # eliminado+alta
    ("def f(a): return 1", "def f(a): return 2"),            # cuerpo => silencio
    ("class C:\n  def __init__(self): pass",
     "class C:\n  def __init__(self, x): pass"),             # construcción
    ("class C:\n  def m(self): pass\n  def n(self): pass",
     "class C:\n  def m(self): pass"),                       # quita público
    ("class C:\n  def m(self): pass", "def C(): pass"),      # def<->class
    ("def f(): pass", "def f(: pass"),                       # nuevo roto => {}
    ("def f(: pass", "def f(): pass"),                       # viejo roto
    ("def f(): pass", "def f(): pass\ndef g(): pass"),       # alta pura
    ("x = 1", "x = 2"),                                       # sin tops
]

CASOS_JS = [
    ("export function f(){ return 1 }", "export function f(){ return 2 }"),
    ("const a = 1\nclass C {}", "const a = 1"),               # eliminado
    ("type T = number", "type T = string"),                  # cambió región
    ("function f(){}", "function f(){}\nclass C {}"),         # alta pura
    ("const x = () => 1", "const x = () => 1"),               # sin cambio
    ("", "function nuevo(){}"),                               # solo alta
]


@pytest.mark.parametrize("viejo,nuevo", CASOS_PY)
def test_paridad_python(viejo: str, nuevo: str) -> None:
    assert tiers.cambios("m.py", viejo, nuevo) == python.cambios_que_importan(
        viejo, nuevo
    )


@pytest.mark.parametrize("viejo,nuevo", CASOS_JS)
@pytest.mark.parametrize("ext", ["js", "ts", "tsx", "jsx"])
def test_paridad_js_ts(ext: str, viejo: str, nuevo: str) -> None:
    assert tiers.cambios(
        f"m.{ext}", viejo, nuevo
    ) == javascript.cambios_que_importan(viejo, nuevo)


def test_referencias_via_tier_coinciden() -> None:
    py = "from mod import Usuario\nx = Usuario()\n"
    js = "import { Boton } from './Boton'\nconst a = Boton()\n"
    assert tiers.tier_para("a.py").referencias(py) == python.referencias(py)
    assert tiers.tier_para("a.ts").referencias(js) == javascript.referencias(js)


def test_lenguaje_no_cruza_y_desconocido() -> None:
    assert tiers.lenguaje_de("a.py") == "py"
    assert tiers.lenguaje_de("a.ts") == tiers.lenguaje_de("a.jsx") == "jsts"
    assert tiers.lenguaje_de("a.rb") is None
    assert tiers.tier_para("a.rb") is None
    assert tiers.cambios("a.rb", "x", "y") == {}


def test_tier_py_es_detallado_y_jsts_cae_a_regex_sin_treesitter() -> None:
    # En el sandbox (sin tree-sitter instalado) JS/TS debe resolver al tier
    # regex (nivel 3), no detallado; Python siempre al ast (nivel 1).
    assert tiers.tier_para("a.py").nivel == 1
    t = tiers.tier_para("a.ts")
    assert t.nivel in (2, 3)  # 2 si hay tree-sitter (VPS), 3 si no (sandbox)


# --- El VALOR de la capa: el camino fino JS/TS que tree-sitter habilita.
# tree-sitter es el único I/O no testeable acá (sin internet); pero lo que
# va a EMITIR son estos `Simbolo` detallados, y la regla sobre ellos sí se
# prueba sin parser. Esto fija el contrato que el VPS debe cumplir.


def _fn(nombre: str, firma: str, cuerpo: str = "x") -> Simbolo:
    return Simbolo(nombre, "funcion", f"{nombre}{firma}{{{cuerpo}}}",
                    firma=firma, detallado=True)


def _cls(nombre: str, init: str, sup: set[str], cuerpo: str = "x") -> Simbolo:
    # fuente refleja init+superficie+cuerpo (como el texto real de la clase
    # que emitirá tree-sitter): si cambia cualquiera, `fuente` cambia.
    cuerpo_real = init + "".join(sorted(sup)) + cuerpo
    return Simbolo(nombre, "clase", f"class {nombre}{{{cuerpo_real}}}",
                   init=init, superficie=frozenset(sup), detallado=True)


def test_jsts_fino_firma_cambiada() -> None:
    a = {"f": _fn("f", "(a)")}
    d = {"f": _fn("f", "(a, b)")}
    assert cambios_que_importan_modelo(a, d) == {
        "f": "cambió la firma de «f»: (a) → (a, b) — revisá las llamadas"
    }


def test_jsts_fino_cuerpo_solo_es_silencio() -> None:
    # La promesa central: con parser, cambiar solo el cuerpo NO avisa.
    a = {"f": _fn("f", "(a)", cuerpo="return 1")}
    d = {"f": _fn("f", "(a)", cuerpo="return 2")}
    assert cambios_que_importan_modelo(a, d) == {}


def test_jsts_fino_clase_construccion_y_superficie() -> None:
    a = {"C": _cls("C", "(x)", {"m()", "v"})}
    assert cambios_que_importan_modelo(a, {"C": _cls("C", "(x, y)", {"m()", "v"})}) == {
        "C": "cambió cómo se construye «C»: __init__(x) → __init__(x, y)"
    }
    assert cambios_que_importan_modelo(a, {"C": _cls("C", "(x)", {"m()"})}) == {
        "C": "«C» ya no expone: v — quien lo usaba va a romper"
    }


def test_jsts_fino_type_interface_enum() -> None:
    a = {"T": Simbolo("T", "tipo", "type T = number", detallado=True)}
    d = {"T": Simbolo("T", "tipo", "type T = string", detallado=True)}
    assert cambios_que_importan_modelo(a, d) == {
        "T": "cambió «T» — su definición es su interfaz; revisá los usos"
    }
    # Sin la coletilla "sin parser de TS": tree-sitter SÍ tiene parser.
    assert "sin parser" not in cambios_que_importan_modelo(a, d)["T"]
