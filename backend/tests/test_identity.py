"""Tests del núcleo de identidad (capa 7, 1/3). Piezas puras, sin red.

Lo crítico a fijar como contrato de seguridad:
- la contraseña nunca se guarda en claro y la verificación es correcta;
- un token con firma falsa o manipulado NO autentica a nadie;
- el usuario se normaliza (mismo dueño aunque cambien mayúsculas/espacios);
- nada de esto explota con entrada corrupta (devuelve False/None).
"""

import pytest

from orux.identity import (
    UserStore,
    crear_token,
    hash_password,
    normalizar,
    usuario_de_token,
    verificar_password,
)


# --- passwords ---


def test_hash_no_es_la_password_y_verifica() -> None:
    reg = hash_password("secreta123")
    assert "secreta123" not in reg  # nunca en claro
    assert verificar_password("secreta123", reg) is True
    assert verificar_password("otra", reg) is False


def test_dos_hashes_de_la_misma_password_difieren() -> None:
    # Sal aleatoria por hash: dos registros distintos, ambos válidos.
    a = hash_password("igualpwd")
    b = hash_password("igualpwd")
    assert a != b
    assert verificar_password("igualpwd", a)
    assert verificar_password("igualpwd", b)


def test_password_vacia_se_rechaza() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_password_demasiado_corta_se_rechaza() -> None:
    # Mínimo 8 chars (OWASP) — antes 1 char pasaba (BACKEND-AUDIT-0005).
    with pytest.raises(ValueError):
        hash_password("corta")


def test_password_demasiado_larga_se_rechaza() -> None:
    # Tope para evitar DoS por PBKDF2 sobre input gigante.
    with pytest.raises(ValueError):
        hash_password("x" * 200)


def test_marker_externo_nunca_verifica() -> None:
    # Defensa en profundidad: si el formato del marker evoluciona, la rama
    # tolerante del parser podría aceptarlo accidentalmente (BACKEND-AUDIT-0007).
    from orux.identity.passwords import MARCADOR_EXTERNO
    assert verificar_password("cualquier-pwd", MARCADOR_EXTERNO) is False
    assert verificar_password("", MARCADOR_EXTERNO) is False


def test_verificar_registro_corrupto_es_false() -> None:
    assert verificar_password("x", "basura") is False
    assert verificar_password("x", "") is False


# --- tokens ---


def test_token_roundtrip() -> None:
    t = crear_token("joaquin", secret="s3cr3t")
    assert usuario_de_token(t, "s3cr3t") == "joaquin"


def test_token_con_otro_secreto_no_vale() -> None:
    t = crear_token("joaquin", secret="bueno")
    assert usuario_de_token(t, "malo") is None


def test_token_manipulado_no_vale() -> None:
    t = crear_token("joaquin", secret="s")
    payload, firma = t.split(".", 1)
    # Mismo formato, firma inventada -> rechazado.
    assert usuario_de_token(payload + ".deadbeef", "s") is None
    # Basura total -> None, no excepción.
    assert usuario_de_token("no-es-un-token", "s") is None
    assert usuario_de_token("", "s") is None


# --- store ---


def test_registrar_y_verificar(tmp_path) -> None:
    s = UserStore(tmp_path / "users.json")
    s.registrar("Joaquin", "clave123")
    assert s.verificar("joaquin", "clave123") is True
    assert s.verificar("joaquin", "mala") is False
    assert s.verificar("nadie", "x") is False


def test_usuario_se_normaliza(tmp_path) -> None:
    s = UserStore(tmp_path / "users.json")
    s.registrar("  Joaquin  ", "clave123")
    # Mismo dueño aunque cambien espacios/mayúsculas.
    assert s.existe("JOAQUIN")
    assert s.verificar("joaquin", "clave123")
    assert normalizar("  AnA ") == "ana"


def test_no_se_puede_registrar_dos_veces(tmp_path) -> None:
    s = UserStore(tmp_path / "users.json")
    s.registrar("ana", "passw0rd")
    with pytest.raises(ValueError):
        s.registrar("ana", "passw0rd2")
    with pytest.raises(ValueError):
        s.registrar("ANA", "passw0rd3")  # misma forma canónica


def test_persiste_entre_instancias(tmp_path) -> None:
    # "Reinicia el server": otra instancia sobre el mismo archivo conserva
    # usuarios. Es lo que hace que la identidad sea de verdad estable.
    ruta = tmp_path / "users.json"
    UserStore(ruta).registrar("ana", "clave123")
    assert UserStore(ruta).verificar("ana", "clave123") is True


def test_archivo_corrupto_arranca_vacio(tmp_path) -> None:
    ruta = tmp_path / "users.json"
    ruta.write_text("{no es json", encoding="utf-8")
    s = UserStore(ruta)  # no explota
    assert s.existe("quien") is False
    s.registrar("nuevo", "passw0rd")  # y sigue usable
    assert s.verificar("nuevo", "passw0rd")


# Sprint de pulido pre-mercado: reglas de usuario al CREAR cuenta. No afecta
# a usuarios viejos (login/sesión/existe siguen plano).


@pytest.mark.parametrize(
    "malo",
    [
        "",                          # vacío
        " ",                         # solo espacios
        "a",                         # muy corto
        "a" * 33,                    # muy largo
        ".ana",                      # arranca con puntuación
        "_ana",
        "-ana",
        "ana bonita",                # espacios internos
        "ana<script>",               # HTML
        "ana/beto",                  # path traversal-ish
        "ana\\beto",                 # backslash
        "ana\nbeto",                 # control char
        "anɐ",                       # unicode no-ASCII
        "GH:foo",                    # prefijo reservado (case-insensitive vía normalizar)
        "gh:bar",
    ],
)
def test_registrar_rechaza_usuario_invalido(tmp_path, malo):
    s = UserStore(tmp_path / "users.json")
    with pytest.raises(ValueError):
        s.registrar(malo, "clave123")


def test_registrar_acepta_usuario_normal(tmp_path) -> None:
    # Charset razonable y rango razonable.
    s = UserStore(tmp_path / "users.json")
    assert s.registrar("ana", "passw0rd") == "ana"
    assert s.registrar("Ana.Lopez", "passw0rd") == "ana.lopez"  # normalizada
    assert s.registrar("dev_2", "passw0rd") == "dev_2"
    assert s.registrar("a-b-c", "passw0rd") == "a-b-c"
    assert s.registrar("Joaquin99", "passw0rd") == "joaquin99"
