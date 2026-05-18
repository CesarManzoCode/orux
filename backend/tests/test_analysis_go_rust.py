"""Capa 20: extractores coarse de Go y Rust (regex, mismo patrón que JS).

NO prueban análisis fino (eso lo da el fan-out LSP real, no testeable en
sandbox): fijan que se detectan los símbolos top y las referencias sin
ruido — lo mínimo para que el fan-out tenga un símbolo que resolver.
"""

from __future__ import annotations

from orux.analysis import go, rust, tiers


def test_go_definiciones_top() -> None:
    src = (
        "package main\n"
        "import \"fmt\"\n"
        "func Crea(n string) string { return n }\n"
        "func (s *Srv) Saludar() {}\n"
        "type Usuario struct { Nombre string }\n"
        "const Version = \"1\"\n"
    )
    d = set(go.definiciones_top(src))
    assert d == {"Crea", "Saludar", "Usuario", "Version"}


def test_go_referencias_sin_ruido() -> None:
    src = 'func F() { x := Otro(); s := "Otro func type" } // type\n'
    r = go.referencias(src)
    assert "Otro" in r
    assert "func" not in r and "type" not in r  # keywords fuera
    assert "s" in r  # identificador normal


def test_rust_definiciones_top() -> None:
    src = (
        "pub fn crea(n: String) -> String { n }\n"
        "async unsafe fn raro() {}\n"
        "pub struct Usuario { nombre: String }\n"
        "enum Color { Rojo }\n"
        "trait Saluda {}\n"
        "pub const VERSION: &str = \"1\";\n"
    )
    d = set(rust.definiciones_top(src))
    assert d == {"crea", "raro", "Usuario", "Color", "Saluda", "VERSION"}


def test_rust_referencias_sin_ruido() -> None:
    src = 'fn f() { let x = Otro::new(); let s = "Otro fn struct"; }\n'
    r = rust.referencias(src)
    assert "Otro" in r
    assert "fn" not in r and "struct" not in r and "let" not in r


def test_tiers_mapea_go_y_rust() -> None:
    assert tiers.lenguaje_de("main.go") == "go"
    assert tiers.lenguaje_de("lib.rs") == "rust"
    # Detección coarse disponible (regex, nivel 3) sin LSP en sandbox.
    assert tiers.tier_para("main.go").nivel == 3
    assert tiers.tier_para("lib.rs").nivel == 3
    # Distinto lenguaje no se cruza.
    assert tiers.lenguaje_de("main.go") != tiers.lenguaje_de("lib.rs")
