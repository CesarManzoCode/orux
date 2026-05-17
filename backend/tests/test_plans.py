"""Capa 22: límites de plan (puro, 100% sandbox). Fija el esqueleto del
freemium: free permanente y usable (la tesis NO se tiera), límites solo de
escala/recurso. Números decretados con el usuario."""

from __future__ import annotations

from laidea import plans


def test_free_es_el_target_declarado() -> None:
    f = plans.limites("free")
    assert f["max_devs"] == 5          # decisión del usuario
    assert f["max_workspaces"] == 1
    assert f["max_langs"] == 2
    assert f["impacto"] == "directo"
    assert f["jvm"] is False


def test_premium_sin_topes_de_escala() -> None:
    p = plans.limites("premium")
    assert p["max_devs"] == plans.INF
    assert p["max_langs"] == plans.INF
    assert p["impacto"] == "transitivo"
    assert p["jvm"] is True and p["conocimiento"] is True


def test_plan_desconocido_cae_a_free_no_a_premium() -> None:
    # Fallar hacia el lado barato/seguro: un plan corrupto NO regala premium.
    assert plans.limites("???") == plans.limites("free")


def test_permite_miembro_tope_5_en_free() -> None:
    assert plans.permite_miembro("free", 4) is True   # entra el 5º
    assert plans.permite_miembro("free", 5) is False  # el 6º no
    assert plans.permite_miembro("premium", 999) is True


def test_permite_lenguaje_tope_2_en_free() -> None:
    assert plans.permite_lenguaje("free", 1) is True   # 2º lenguaje ok
    assert plans.permite_lenguaje("free", 2) is False  # 3º no (degrada)
    assert plans.permite_lenguaje("premium", 9) is True


def test_helpers_jvm_e_impacto() -> None:
    assert plans.permite_jvm("free") is False
    assert plans.permite_jvm("premium") is True
    assert plans.impacto_modo("free") == "directo"
    assert plans.impacto_modo("premium") == "transitivo"
