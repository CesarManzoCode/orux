"""Tests del análisis JS/TS (capa 6, segundo lenguaje) y del despacho.

Mismo criterio que `test_analysis.py`: heurístico por nombres, honesto, no
compilador. Fija los contratos que importan: detectar símbolos top
(incluye `type`/`interface`/`enum` de TS), cambios por agregado/quitado/
edición de cuerpo, referencias sin ruido de strings/comentarios, y que
`impacto` despacha por extensión y NO cruza lenguajes.
"""

from laidea.analysis import impacto
from laidea.analysis.javascript import (
    definiciones_top,
    referencias,
    simbolos_cambiados,
)


def test_definiciones_top_formas_js_ts() -> None:
    src = (
        "export function login() {}\n"
        "class Usuario {}\n"
        "const helper = (x) => x + 1\n"
        "export interface Sesion { id: string }\n"
        "export type Rol = 'admin' | 'user'\n"
        "  function noTop() {}\n"            # indentado: NO top
    )
    d = set(definiciones_top(src))
    assert d == {"login", "Usuario", "helper", "Sesion", "Rol"}


def test_referencias_ignora_strings_y_comentarios() -> None:
    src = (
        "// Usuario en un comentario no cuenta\n"
        "const s = 'tampoco Usuario en string'\n"
        "function f() { return Usuario.activo }\n"
    )
    r = referencias(src)
    assert "Usuario" in r
    assert "f" in r
    # 'tampoco'/'comentario' no deben filtrarse como identificadores reales
    assert "tampoco" not in r and "comentario" not in r


def test_simbolos_cambiados_cuerpo_y_altas_bajas() -> None:
    v = "export function f() { return 1 }\nexport function g() { return 2 }\n"
    n = "export function f() { return 99 }\nexport function g() { return 2 }\n"
    assert simbolos_cambiados(v, n) == {"f"}                 # cambió el cuerpo
    assert simbolos_cambiados(v, v + "class C {}\n") == {"C"}  # agregado
    assert simbolos_cambiados(v, "export function f() { return 1 }\n") == {"g"}


def test_impacto_typescript_dentro_del_lenguaje() -> None:
    ws = {
        "models.ts": "export class Usuario {}\n",
        "auth.ts": "import { Usuario } from './models'\nconst u = new Usuario()\n",
        "infra.ts": "export const x = 1\n",          # no usa Usuario
        "legacy.py": "Usuario = 1\n",                  # otro lenguaje: se ignora
    }
    viejo = "export class Usuario {}\n"
    nuevo = "export class Usuario { activo = true }\n"
    assert impacto(ws, "models.ts", viejo, nuevo) == {"Usuario": ["auth.ts"]}


def test_impacto_no_cruza_lenguajes() -> None:
    # Un símbolo .ts cambiado NO debe "afectar" un .py que use ese nombre.
    ws = {"a.ts": "export function shared() {}\n", "b.py": "shared()\n"}
    res = impacto(ws, "a.ts",
                  "export function shared() {}\n",
                  "export function shared() { return 1 }\n")
    assert res == {}


def test_impacto_jsx_tsx_mismo_extractor() -> None:
    ws = {
        "Boton.tsx": "export function Boton() { return null }\n",
        "App.jsx": "import { Boton } from './Boton'\nconst a = <Boton/>\n",
    }
    res = impacto(ws, "Boton.tsx",
                  "export function Boton() { return null }\n",
                  "export function Boton() { return <div/> }\n")
    assert res == {"Boton": ["App.jsx"]}
