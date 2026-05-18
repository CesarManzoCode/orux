"""Tests del núcleo de análisis semántico (capa 6, Python).

Pieza pura: sin red ni estado. Lo crítico a fijar como contrato:
- detecta cambios reales de símbolos top (no ruido por reformatear nada);
- mapea símbolo cambiado -> archivos que lo usan;
- NO explota ni opina cuando el código está a medio escribir (SyntaxError).
"""

from orux.analysis import (
    cambios_que_importan,
    definiciones_top,
    impacto,
    motivos,
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
    # Cambio de firma REAL (no solo cuerpo): aun así, nadie la usa -> {}.
    res = impacto(workspace, "a.py", "def solitaria():\n    return 1\n",
                  "def solitaria(x):\n    return x\n")
    assert res == {}


# --- El arreglo: el aviso solo salta cuando IMPORTA, y dice POR QUÉ ---
# (antes era adorno: cualquier cambio de cuerpo pingaba a todos)


def test_cambio_de_solo_cuerpo_no_avisa() -> None:
    # Cambiar lo interno de una función NO afecta a quien la llama: silencio.
    # Esto es lo que mata el "¿y esto a mí qué me importa?".
    viejo = "def f(a, b):\n    return a + b\n"
    nuevo = "def f(a, b):\n    total = a + b\n    return total\n"
    assert cambios_que_importan(viejo, nuevo) == {}
    ws = {"a.py": viejo, "b.py": "from a import f\nf(1, 2)\n"}
    assert impacto(ws, "a.py", viejo, nuevo) == {}  # no se avisa nada


def test_cambio_de_firma_avisa_con_el_porque() -> None:
    viejo = "def cobrar(monto):\n    return monto\n"
    nuevo = "def cobrar(monto, moneda):\n    return monto\n"
    motivo = cambios_que_importan(viejo, nuevo)
    assert set(motivo) == {"cobrar"}
    assert "firma" in motivo["cobrar"]
    assert "(monto)" in motivo["cobrar"] and "(monto, moneda)" in motivo["cobrar"]


def test_simbolo_eliminado_avisa_que_va_a_romper() -> None:
    motivo = cambios_que_importan("def viejo():\n    pass\n", "x = 1\n")
    assert "viejo" in motivo
    assert "eliminó" in motivo["viejo"] or "renombró" in motivo["viejo"]


def test_clase_cambia_construccion_avisa() -> None:
    viejo = "class Pago:\n    pass\n"
    nuevo = "class Pago:\n    def __init__(self, monto):\n        self.monto = monto\n"
    motivo = cambios_que_importan(viejo, nuevo)
    assert "Pago" in motivo and "construye" in motivo["Pago"]


def test_clase_quita_metodo_publico_avisa_pero_privado_no() -> None:
    viejo = (
        "class API:\n"
        "    def publico(self):\n        return 1\n"
        "    def _interno(self):\n        return 2\n"
    )
    # Se quita el método público -> avisa.
    sin_pub = "class API:\n    def _interno(self):\n        return 2\n"
    m = cambios_que_importan(viejo, sin_pub)
    assert "API" in m and "publico()" in m["API"]
    # Se cambia SOLO el cuerpo del privado -> no rompe a nadie: silencio.
    priv = (
        "class API:\n"
        "    def publico(self):\n        return 1\n"
        "    def _interno(self):\n        return 99\n"
    )
    assert cambios_que_importan(viejo, priv) == {}


def test_cambios_que_importan_vacio_si_roto() -> None:
    # Código a medio escribir: no se opina (cero falsos positivos).
    assert cambios_que_importan("def f(): pass", "def f(:") == {}


def test_motivos_despacha_por_extension() -> None:
    # `motivos` es el "por qué" que el server adjunta al aviso.
    m = motivos("api.py", "def f(a):\n    pass\n", "def f(a, b):\n    pass\n")
    assert "f" in m and "firma" in m["f"]
    assert motivos("nota.md", "x", "y") == {}  # lenguaje sin extractor


def test_impacto_solo_para_archivos_py() -> None:
    workspace = {"notas.md": "texto", "a.py": "x = 1"}
    assert impacto(workspace, "notas.md", "viejo", "nuevo") == {}


def test_deps_interfaz_python() -> None:
    # Capa 24b: tipos en la interfaz (no en el cuerpo) -> el transitivo
    # propaga por dependencia de tipos en Python.
    from orux.analysis.python import _deps_interfaz, _nodos_top

    src = (
        "def make_user(rol: Rol) -> Usuario:\n"
        "    tmp = Interno()  # cuerpo: NO es interfaz\n"
        "    return Usuario()\n"
        "class Caja(Base):\n"
        "    item: Producto\n"
        "    def __init__(self, d: Deposito): ...\n"
        "    def _oculto(self, x: Secreto): ...\n"
    )
    nt = _nodos_top(src)
    df = _deps_interfaz(nt["make_user"])
    assert {"Rol", "Usuario"} <= df and "Interno" not in df  # cuerpo afuera
    dc = _deps_interfaz(nt["Caja"])
    assert {"Base", "Producto", "Deposito"} <= dc
    assert "Secreto" not in dc  # método privado: no es interfaz pública


def test_severidad_de() -> None:
    from orux.analysis.modelo import severidad_de
    assert severidad_de("se eliminó o renombró «X» — el código...") == "alta"
    assert severidad_de("cambió la firma de «f»: (a) → (a, b)") == "alta"
    assert severidad_de("«C» ya no expone: v — quien lo usaba...") == "alta"
    assert severidad_de("cambió «T» — su definición es su interfaz") == "media"
    assert severidad_de("«x» cambió — sin parser de TS...") == "media"
    assert severidad_de("«h» usa «S» (que cambió) en su cuerpo — revisá; "
                        "la onda corta acá") == "baja"
    assert severidad_de("algo raro no clasificado") == "media"  # no sub-avisa
