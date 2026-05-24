"""Tests de robustez añadidos en la auditoría 2026-05-24.

Documentan comportamiento que un refactor futuro podría debilitar sin
disparar otra regresión: helpers centralizados, sanitización de open
redirect en OAuth, callback defensivo de tareas de fondo de billing, y
sobrevivencia de los loops de eviction ante fallos por equipo.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from orux._env import _env_float, _env_int


# --------------------------- _env helpers ---------------------------------


def test_env_int_default_si_no_existe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("__ORUX_TEST_X__", raising=False)
    assert _env_int("__ORUX_TEST_X__", 10, 1, 100) == 10


def test_env_int_clampa_arriba_y_abajo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("__ORUX_TEST_X__", "9999999")
    assert _env_int("__ORUX_TEST_X__", 10, 1, 100) == 100
    monkeypatch.setenv("__ORUX_TEST_X__", "-50")
    assert _env_int("__ORUX_TEST_X__", 10, 1, 100) == 1


def test_env_int_valor_invalido_cae_al_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("__ORUX_TEST_X__", "no-soy-int")
    assert _env_int("__ORUX_TEST_X__", 42, 1, 100) == 42


def test_env_float_default_y_clamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("__ORUX_TEST_X__", raising=False)
    assert _env_float("__ORUX_TEST_X__", 1.5, 0.0, 10.0) == 1.5
    monkeypatch.setenv("__ORUX_TEST_X__", "999.0")
    assert _env_float("__ORUX_TEST_X__", 1.5, 0.0, 10.0) == 10.0


def test_env_int_compatibilidad_reexport_desde_config() -> None:
    """`server.config._env_int` y `db.pool._env_int` deben SEGUIR siendo
    el helper centralizado: si alguien lo redefine localmente y se olvida
    de uno, este test lo gritará."""
    from orux.db import pool as pool_mod
    from orux.server import config as cfg
    from orux.state import workspace as ws

    assert cfg._env_int is _env_int
    assert pool_mod._env_int is _env_int
    assert ws._env_int is _env_int


# --------------------------- _sanitizar_app_url ---------------------------


def test_sanitizar_app_url_relativo_se_acepta() -> None:
    from orux.api.app import _sanitizar_app_url

    assert _sanitizar_app_url("/app/", "") == "/app/"
    assert _sanitizar_app_url("/foo?x=1", "https://orux.space") == "/foo?x=1"


def test_sanitizar_app_url_vacio_cae_a_default() -> None:
    from orux.api.app import _sanitizar_app_url

    assert _sanitizar_app_url("", "") == "/app/"
    assert _sanitizar_app_url("   ", "") == "/app/"


def test_sanitizar_app_url_absoluto_mismo_origen_se_acepta() -> None:
    from orux.api.app import _sanitizar_app_url

    out = _sanitizar_app_url(
        "https://orux.space/app/", "https://orux.space",
    )
    assert out == "https://orux.space/app/"


def test_sanitizar_app_url_otro_origen_cae_a_default() -> None:
    """Defensa de open redirect: si el operador setea por error un host
    distinto al público, el redirect post-OAuth NO puede mandar el token
    de sesión al atacante."""
    from orux.api.app import _sanitizar_app_url

    assert _sanitizar_app_url(
        "https://atacante.com/app/", "https://orux.space",
    ) == "/app/"
    assert _sanitizar_app_url(
        "//atacante.com/app/", "https://orux.space",
    ) == "/app/"


# --------------------------- seats: callback defensivo --------------------


@pytest.mark.asyncio
async def test_disparar_ajuste_loguea_exception_no_atrapada(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`ajustar_asientos` ya envuelve en try/except, pero el callback es la
    última red de seguridad si un bug futuro libera una excepción al loop.
    """
    from orux.server.seats import disparar_ajuste

    async def _explota() -> None:
        raise RuntimeError("bug nuevo")

    tareas: set[asyncio.Task] = set()
    with caplog.at_level(logging.ERROR, logger="orux.server.seats"):
        disparar_ajuste(_explota(), tareas)
        # Esperar a que el done_callback corra.
        while tareas:
            await asyncio.sleep(0.01)
    msgs = [r.getMessage() for r in caplog.records]
    assert any("excepción no atrapada" in m and "bug nuevo" in m for m in msgs)


@pytest.mark.asyncio
async def test_disparar_ajuste_no_loguea_si_cancelada(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from orux.server.seats import disparar_ajuste

    async def _largo() -> None:
        await asyncio.sleep(10)

    tareas: set[asyncio.Task] = set()
    with caplog.at_level(logging.ERROR, logger="orux.server.seats"):
        disparar_ajuste(_largo(), tareas)
        t = next(iter(tareas))
        t.cancel()
        while tareas:
            await asyncio.sleep(0.01)
    assert not any(
        "excepción no atrapada" in r.getMessage() for r in caplog.records
    )


# --------------------------- eviction: loops sobreviven -------------------


@pytest.mark.asyncio
async def test_barrer_lsp_ociosas_sobrevive_a_fallo_por_equipo(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un equipo cuya `evictar_lsp_ociosas` explota NO debe matar el loop:
    sigue evictando el resto en la próxima vuelta.

    Estrategia: el sleep mock cuenta vueltas y dispara CancelledError tras
    N — así el loop termina determinísticamente sin race contra
    `tarea.cancel()`."""
    from orux.server import eviction

    N_VUELTAS = 3
    vueltas = {"n": 0}

    async def _sleep_corta(s: float) -> None:
        vueltas["n"] += 1
        if vueltas["n"] > N_VUELTAS:
            raise asyncio.CancelledError
        # NO await asyncio.sleep(0): el patch es global y recursaría
        # infinitamente sobre nuestro propio mock. Esto retorna en el mismo
        # tick — basta para que el while True itere.
        return None

    monkeypatch.setattr(eviction.asyncio, "sleep", _sleep_corta)

    llamadas: list[str] = []

    class _RtFalla:
        def evictar_lsp_ociosas(self, ttl: float) -> list[str]:
            llamadas.append("falla")
            raise RuntimeError("bug en evictar")

    class _RtOk:
        def evictar_lsp_ociosas(self, ttl: float) -> list[str]:
            llamadas.append("ok")
            return []

    runtimes = {"eq-malo": _RtFalla(), "eq-bueno": _RtOk()}

    with pytest.raises(asyncio.CancelledError):
        await eviction.barrer_lsp_ociosas(runtimes, ttl=60.0)

    # Ambos equipos visitados (uno explotó, el otro siguió) en MÚLTIPLES
    # vueltas → el loop sobrevivió al fallo del equipo malo.
    assert llamadas.count("falla") >= 2
    assert llamadas.count("ok") >= 2


@pytest.mark.asyncio
async def test_barrer_runtimes_ociosos_sobrevive_a_fallo_general(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si `runtime_evictable` explota mientras el loop construye la lista
    de candidatos (estado corrupto, bug en lógica), el loop reintenta en
    la próxima vuelta — no queda muerto en silencio."""
    from orux.server import eviction

    N_VUELTAS = 3
    contador = {"n": 0}

    async def _sleep_corta(s: float) -> None:
        contador["n"] += 1
        if contador["n"] > N_VUELTAS:
            raise asyncio.CancelledError
        return None

    monkeypatch.setattr(eviction.asyncio, "sleep", _sleep_corta)

    vueltas: list[int] = []

    def _runtime_evictable_falla(rt, ttl, ahora, *, tiene_proposals_store):
        vueltas.append(1)
        raise RuntimeError("bug en runtime_evictable")

    monkeypatch.setattr(
        eviction, "runtime_evictable", _runtime_evictable_falla,
    )

    runtimes = {"eq1": object()}
    with caplog.at_level(logging.ERROR, logger="orux.server.eviction"):
        with pytest.raises(asyncio.CancelledError):
            await eviction.barrer_runtimes_ociosos(
                ttl=60.0,
                runtimes=runtimes,
                rt_locks={},
                asientos_locks={},
                tiene_proposals_store=True,
            )

    # Si el loop hubiese muerto en la primera vuelta, `vueltas` tendría 1.
    # Como sobrevive, hay varias.
    assert len(vueltas) >= 2
