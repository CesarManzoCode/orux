"""Tests de GitHub OAuth — lógica pura, sin red (la llamada a GitHub vive en
la cáscara HTTP y se prueba en el VPS, igual que `api/app.py`).

Contrato de seguridad a fijar:
- la identidad OAuth SIEMPRE lleva el namespace `gh:` (imposible colisionar
  con una cuenta de contraseña, que era el riesgo de apropiación);
- el `state` CSRF: solo vale si lo firmó este server y no venció;
- una cuenta externa existe (para `SessionMessage`) pero NO se puede entrar
  a ella por contraseña.
"""

import pytest

from orux.identity import (
    UserStore,
    firmar_state,
    identidad_github,
    url_autorizacion,
    validar_state,
    verificar_password,
)
from orux.identity.oauth import SCOPE
from orux.identity.passwords import MARCADOR_EXTERNO


# --- URL de autorización ---------------------------------------------------

def test_url_autorizacion_lleva_todo_y_es_https_de_github() -> None:
    u = url_autorizacion("CID", "https://orux.app/oauth/github/callback",
                          "ST")
    assert u.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=CID" in u
    assert "state=ST" in u
    # redirect_uri y scope van url-encodeados.
    assert "redirect_uri=https%3A%2F%2Forux.app" in u
    assert "scope=read%3Auser+user%3Aemail" in u
    assert SCOPE == "read:user user:email"


# --- Identidad: el namespace gh: es el contrato de seguridad ---------------

def test_identidad_lleva_prefijo_gh_y_normaliza() -> None:
    assert identidad_github({"login": "Torvalds"}) == "gh:torvalds"
    assert identidad_github({"login": "  OctoCat  "}) == "gh:octocat"


def test_identidad_oauth_no_colisiona_con_cuenta_de_password() -> None:
    # El riesgo descartado: una cuenta de contraseña "torvalds" y el GitHub
    # "torvalds" DEBEN ser identidades distintas.
    store = UserStore()
    store.registrar("torvalds", "secreto123")
    assert identidad_github({"login": "torvalds"}) == "gh:torvalds"
    assert store.existe("torvalds") is True
    assert store.existe("gh:torvalds") is False  # espacios disjuntos


def test_identidad_perfil_sin_login_es_error() -> None:
    with pytest.raises(ValueError):
        identidad_github({})
    with pytest.raises(ValueError):
        identidad_github({"login": ""})
    with pytest.raises(ValueError):
        identidad_github({"login": None})


# --- state CSRF firmado y con vencimiento ----------------------------------

def test_state_valido_recien_firmado() -> None:
    s = firmar_state("secreto", ahora=1000.0)
    assert validar_state(s, "secreto", ahora=1000.0) is True


def test_state_con_otro_secreto_no_vale() -> None:
    s = firmar_state("secreto", ahora=1000.0)
    assert validar_state(s, "otro", ahora=1000.0) is False


def test_state_manipulado_o_roto_no_vale() -> None:
    s = firmar_state("secreto", ahora=1000.0)
    assert validar_state(s + "x", "secreto", ahora=1000.0) is False
    assert validar_state("sinpunto", "secreto") is False
    assert validar_state("9999.deadbeef", "secreto") is False
    assert validar_state("", "secreto") is False


def test_state_vencido_o_del_futuro_no_vale() -> None:
    s = firmar_state("secreto", ahora=1000.0)
    # 10 min + 1s después: vencido.
    assert validar_state(s, "secreto", max_edad=600, ahora=1601.0) is False
    # Emitido "en el futuro" (reloj manipulado): tampoco.
    assert validar_state(s, "secreto", ahora=900.0) is False


# --- Cuenta externa: existe pero sin password ------------------------------

def test_asegurar_externo_crea_idempotente_y_sin_password(tmp_path) -> None:
    store = UserStore(tmp_path / "users.json")
    u = store.asegurar_externo("gh:octocat")
    assert u == "gh:octocat"
    assert store.existe("gh:octocat") is True
    # Idempotente: segunda vez no rompe ni duplica.
    assert store.asegurar_externo("gh:octocat") == "gh:octocat"
    # No se puede entrar por contraseña a una cuenta OAuth (ni con el
    # marcador como si fuera la contraseña).
    assert store.verificar("gh:octocat", "") is False
    assert store.verificar("gh:octocat", MARCADOR_EXTERNO) is False
    assert verificar_password(MARCADOR_EXTERNO, MARCADOR_EXTERNO) is False


def test_asegurar_externo_persiste(tmp_path) -> None:
    p = tmp_path / "users.json"
    UserStore(p).asegurar_externo("gh:ana")
    assert UserStore(p).existe("gh:ana") is True
