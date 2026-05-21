"""Capa 26: rename seguro coordinado — núcleo PURO (100% sandbox).

Fija el contrato del detector y del codemod sin red ni LSP (el fan-out real
se prueba con server LSP falso / VPS, igual que capas 17-21). Lo que se fija
acá: el guardarraíl de confianza (sub-ofrecer > reescribir mal) y que el
codemod es mecánico, acotado y conservador.
"""

from __future__ import annotations

from orux import plans
from orux.analysis.modelo import Simbolo
from orux.analysis.rename import (
    aplicar_rename,
    detectar_rename,
    texto_sugerencia,
)


def _clase(nombre: str, superficie: set[str], init: str = "", src: str = "x"):
    return Simbolo(
        nombre=nombre, tipo="clase", fuente=src, init=init,
        superficie=frozenset(superficie), detallado=True,
    )


def test_detecta_rename_de_atributo_confiable() -> None:
    a = {"C": _clase("C", {"variable"}, src="class C: variable=1")}
    d = {"C": _clase("C", {"name"}, src="class C: name=1")}
    r = detectar_rename(a, d)
    assert r is not None
    assert (r.clase, r.viejo, r.nuevo) == ("C", "variable", "name")


def test_detecta_rename_de_metodo_y_pela_los_parentesis() -> None:
    a = {"C": _clase("C", {"foo()", "v"})}
    d = {"C": _clase("C", {"bar()", "v"})}
    r = detectar_rename(a, d)
    assert r is not None and (r.viejo, r.nuevo) == ("foo", "bar")


def test_no_detecta_si_cambio_el_constructor() -> None:
    # __init__ distinto = cambio mayor, NO un rename limpio: que lo vea el
    # impacto normal, no se arriesga un codemod.
    # Capa 26b: la guardia se relajó SOLO para cambios CONSISTENTES con el
    # rename. Acá el __init__ agrega un param `x` que no tiene que ver con
    # el rename `variable→name`: sigue siendo None (correcto).
    a = {"C": _clase("C", {"variable"}, init="(self)")}
    d = {"C": _clase("C", {"name"}, init="(self, x)")}
    assert detectar_rename(a, d) is None


def test_detecta_rename_de_atributo_de_instancia() -> None:
    # Capa 26b (caso real usuario, 2026-05-20): el rename más común en
    # Python es `self.edad = edad` -> `self.asd = asd`. Antes nunca se
    # detectaba porque `superficie` solo miraba el cuerpo top-level. Ahora
    # `atrs_instancia` lo aísla y `detectar_rename` lo cubre.
    from orux.analysis import tiers
    t = tiers.tier_para("main.py")
    a = t.simbolos(
        "class Persona:\n"
        "    def __init__(self, valor):\n"
        "        self.edad = valor\n"
    )
    d = t.simbolos(
        "class Persona:\n"
        "    def __init__(self, valor):\n"
        "        self.asd = valor\n"
    )
    r = detectar_rename(a, d)
    assert r is not None
    assert (r.clase, r.viejo, r.nuevo) == ("Persona", "edad", "asd")


def test_detecta_rename_con_init_consistente() -> None:
    # El caso típico: renombrar el atributo Y su parámetro homónimo a la
    # vez. El __init__ cambia, pero el cambio es EXACTAMENTE el rename.
    # Ahora se detecta (antes era el False-negativo silencioso).
    from orux.analysis import tiers
    t = tiers.tier_para("main.py")
    a = t.simbolos(
        "class Persona:\n"
        "    def __init__(self, nombre, edad):\n"
        "        self.nombre = nombre\n"
        "        self.edad = edad\n"
    )
    d = t.simbolos(
        "class Persona:\n"
        "    def __init__(self, nombre, asd):\n"
        "        self.nombre = nombre\n"
        "        self.asd = asd\n"
    )
    r = detectar_rename(a, d)
    assert r is not None
    assert (r.viejo, r.nuevo) == ("edad", "asd")


def test_no_detecta_si_init_mezcla_otros_cambios() -> None:
    # Caso real del usuario (cambio mezclado): renombra `edad`→`asd` PERO
    # también quita `variablenueva`. Es cambio mayor, NO codemod automático.
    # Solo el aviso ALTA normal de impacto debe llegar (lo verifica
    # test_sync.py end-to-end).
    from orux.analysis import tiers
    t = tiers.tier_para("main.py")
    a = t.simbolos(
        "class Persona:\n"
        "    def __init__(self, nombre, edad, agenueva, variablenueva):\n"
        "        self.nombre = nombre\n"
        "        self.edad = edad\n"
    )
    d = t.simbolos(
        "class Persona:\n"
        "    def __init__(self, nombre, asd, agenueva):\n"
        "        self.nombre = nombre\n"
        "        self.asd = asd\n"
    )
    assert detectar_rename(a, d) is None


def test_no_detecta_si_hay_dos_cambios() -> None:
    # 2 quitados + 2 agregados: no se puede casar 1:1 sin adivinar -> None.
    a = {"C": _clase("C", {"a", "b"})}
    d = {"C": _clase("C", {"x", "y"})}
    assert detectar_rename(a, d) is None


def test_no_detecta_metodo_por_atributo() -> None:
    # foo() -> foo (de método a atributo) no es "el mismo miembro": None.
    a = {"C": _clase("C", {"foo()"})}
    d = {"C": _clase("C", {"foo"})}
    assert detectar_rename(a, d) is None


def test_no_detecta_sobre_tier_no_detallado() -> None:
    # Heurístico ciego (tipo "?", regex sin parser): NO se arriesga rename.
    a = {"C": Simbolo("C", "?", "algo", detallado=False)}
    d = {"C": Simbolo("C", "?", "otro", detallado=False)}
    assert detectar_rename(a, d) is None


def test_no_detecta_alta_pura_ni_baja_pura() -> None:
    base = {"C": _clase("C", {"a"})}
    assert detectar_rename({}, base) is None              # solo alta
    assert detectar_rename(base, {"C": _clase("C", set())}) is None  # solo baja


def test_codemod_renombra_acceso_a_miembro() -> None:
    src = "from m import C\nx = C()\nprint(x.variable)\nx.variable += 1\n"
    out = aplicar_rename(src, "variable", "name")
    assert "x.name" in out
    assert "x.variable" not in out
    assert "import C" in out  # no toca lo no relacionado


def test_codemod_respeta_limite_de_palabra_y_es_idempotente() -> None:
    src = "obj.variable\nobj.variableX\nobj.subvariable\n"
    out = aplicar_rename(src, "variable", "name")
    assert "obj.name\n" in out
    assert "obj.variableX" in out      # \b: no pisa un nombre más largo
    assert "obj.subvariable" in out    # ni un sufijo
    assert aplicar_rename(out, "variable", "name") == out  # idempotente


def test_texto_sugerencia_es_accionable() -> None:
    from orux.analysis.rename import Rename

    t = texto_sugerencia(Rename(clase="C", viejo="variable", nuevo="name"))
    assert "variable" in t and "name" in t and "C" in t
    assert "actualizá los usos" in t


def test_plan_gatea_el_rename_automatico() -> None:
    assert plans.permite_rename("free") is False     # free = solo texto
    assert plans.permite_rename("premium") is True    # premium = lo aplica
    # Plan corrupto cae a free (lado seguro/barato): NO regala el codemod.
    assert plans.permite_rename("???") is False
