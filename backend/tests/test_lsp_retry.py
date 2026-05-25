"""Retry y detección de muerte para sesiones LSP.

Antes: si `arrancar_lsp` devolvía None (binario ausente, OOM, lo que sea)
se cacheaba para siempre — un equipo quedaba degradado mudo hasta
`reciclar_lsp`. Y si la sesión se cacheaba pero MORÍA después (subprocess
crash), `lsp_sesion` devolvía la sesión muerta y todos los análisis
fallaban silenciosamente.

Ahora cada entrada del cache es un `_LspEstado` con:
- detección de muerte (`SesionLSP.disponible()`),
- cooldown exponencial entre reintentos (60s → 30 min),
- logging del estado real.
"""

from __future__ import annotations

import time

from orux.server.runtime import TeamRuntime, _LspEstado


def test_lspestado_cooldown_es_exponencial_con_tope():
    """1 fallo -> 60s, 2 -> 120, 3 -> 240, ..., tope 30 min."""
    st = _LspEstado()
    assert st.cooldown_seg() == 0.0  # sin fallos: sin espera

    st.intentos_fallidos = 1
    assert st.cooldown_seg() == 60.0
    st.intentos_fallidos = 2
    assert st.cooldown_seg() == 120.0
    st.intentos_fallidos = 3
    assert st.cooldown_seg() == 240.0
    # Tope: aunque sigan fallando, no esperamos más de 30 min.
    st.intentos_fallidos = 100
    assert st.cooldown_seg() == 1800.0


def test_lspestado_puede_reintentar_respeta_cooldown():
    st = _LspEstado()
    st.intentos_fallidos = 1
    st.ultimo_fallo = 1000.0

    # Justo en el último fallo: hay que esperar el cooldown (60s).
    assert st.puede_reintentar(1000.0) is False
    # Mitad del cooldown: aún no.
    assert st.puede_reintentar(1030.0) is False
    # Pasado el cooldown: sí.
    assert st.puede_reintentar(1060.0) is True
    assert st.puede_reintentar(2000.0) is True


def test_lsp_sesion_sin_dir_devuelve_none_sin_marcar_fallos():
    """El guard de "sin workspace dir" es por DISEÑO (tests en memoria);
    no debe inflar el contador de fallos ni programar un cooldown."""
    rt = TeamRuntime()  # storage=None => _ws_dir=None
    assert rt.lsp_sesion("py") is None
    assert "py" not in rt._lsp  # no se registró nada


async def test_lsp_sesion_falla_y_marca_cooldown():
    """En el sandbox sin pyright, arrancar_lsp devuelve None: la entrada
    queda con cooldown y la siguiente llamada inmediata respeta la espera."""
    rt = TeamRuntime()
    rt._ws_dir = "/tmp"
    assert rt.lsp_sesion("py") is None
    estado = rt._lsp["py"]
    assert estado.intentos_fallidos == 1
    assert estado.ultimo_fallo > 0
    assert estado.cooldown_seg() == 60.0

    # Llamada inmediata: aún en cooldown -> None y SIN nuevo intento
    # (el contador no sube de 1).
    assert rt.lsp_sesion("py") is None
    assert estado.intentos_fallidos == 1


async def test_lsp_sesion_pasado_el_cooldown_reintenta():
    rt = TeamRuntime()
    rt._ws_dir = "/tmp"
    rt.lsp_sesion("py")  # primer fallo: cooldown 60s
    estado = rt._lsp["py"]
    # Forzamos que el cooldown ya pasó.
    estado.ultimo_fallo = time.monotonic() - 999

    rt.lsp_sesion("py")  # ahora SÍ reintenta (y vuelve a fallar)
    assert estado.intentos_fallidos == 2
    assert estado.cooldown_seg() == 120.0  # crece


async def test_lsp_sesion_detecta_sesion_muerta_y_reintenta():
    """Si la sesión cacheada está caída (subprocess murió), se descarta
    y se reintenta — no se devuelve la sesión muerta."""

    class _SesionMuerta:
        def __init__(self):
            self._cerrada = False

        def disponible(self):
            return False

        def cerrar(self):
            self._cerrada = True

    rt = TeamRuntime()
    rt._ws_dir = "/tmp"
    estado = _LspEstado()
    sesion_muerta = _SesionMuerta()
    estado.sesion = sesion_muerta
    rt._lsp["py"] = estado

    # Llamamos lsp_sesion: detecta muerte, descarta, intenta re-arrancar
    # (que falla en sandbox), marca cooldown.
    res = rt.lsp_sesion("py")
    assert res is None
    assert sesion_muerta._cerrada is True
    assert estado.sesion is None
    assert estado.intentos_fallidos == 1


async def test_lsp_sesion_devuelve_sesion_viva_sin_tocar_contador():
    """El camino feliz: hay sesión viva, se devuelve, no se cuenta como
    fallo ni se programa cooldown."""

    class _SesionViva:
        def disponible(self):
            return True

    rt = TeamRuntime()
    rt._ws_dir = "/tmp"
    estado = _LspEstado()
    estado.sesion = _SesionViva()
    rt._lsp["py"] = estado

    res = rt.lsp_sesion("py")
    assert res is estado.sesion
    assert estado.intentos_fallidos == 0


async def test_lsp_sesion_arranque_ok_resetea_contador_de_fallos():
    """Tras N fallos, un arranque exitoso debe volver el estado a limpio
    (intentos_fallidos=0); si no, el próximo cooldown sería gigante."""

    class _SesionViva:
        def disponible(self):
            return True

    rt = TeamRuntime()
    rt._ws_dir = "/tmp"
    estado = _LspEstado()
    estado.intentos_fallidos = 3
    estado.ultimo_fallo = time.monotonic() - 99999  # cooldown pasado
    rt._lsp["py"] = estado

    # Reemplazamos arrancar_lsp para simular un arranque exitoso.
    # Tras el refactor hex (2026-05-24), runtime vive en
    # orux.adapters.inbound.websocket.runtime (orux.server.runtime es solo
    # re-export). El binding `arrancar_lsp` se resuelve en el módulo real.
    import orux.adapters.inbound.websocket.runtime as rmod
    orig = rmod.arrancar_lsp
    rmod.arrancar_lsp = lambda lang, raiz: _SesionViva()
    try:
        res = rt.lsp_sesion("py")
        assert res is not None
        assert estado.intentos_fallidos == 0
        assert estado.ultimo_fallo == 0.0
    finally:
        rmod.arrancar_lsp = orig


async def test_cap_de_lenguajes_solo_cuenta_sesiones_vivas():
    """El cap (plan free / premium) tope la RAM REAL — sesiones con
    cooldown no tienen subprocess vivo, no deben consumir el cap."""

    class _SesionViva:
        def disponible(self):
            return True

    rt = TeamRuntime()
    rt._ws_dir = "/tmp"
    # 2 con sesión viva, 1 en cooldown.
    for k in ("py", "ts"):
        st = _LspEstado()
        st.sesion = _SesionViva()
        rt._lsp[k] = st
    st_cooldown = _LspEstado()
    st_cooldown.intentos_fallidos = 1
    st_cooldown.ultimo_fallo = time.monotonic()
    rt._lsp["jsts"] = st_cooldown

    assert rt._lsp_lenguajes_activos() == 2

    # cap=2 alcanzado por las 2 vivas: un NUEVO lenguaje no arranca.
    assert rt.lsp_sesion("go", cap_langs=2) is None
    assert "go" not in rt._lsp


async def test_reciclar_lsp_funciona_con_estados_y_sesiones():
    """`reciclar_lsp` (clone destructivo) cierra TODO el cache, incluido
    estados sin sesión."""

    class _SesionViva:
        def __init__(self):
            self._cerrada = False

        def disponible(self):
            return True

        def cerrar(self):
            self._cerrada = True

    rt = TeamRuntime()
    rt._ws_dir = "/tmp"
    viva = _SesionViva()
    st1 = _LspEstado()
    st1.sesion = viva
    rt._lsp["py"] = st1
    # Estado en cooldown (sin sesión): también se borra.
    st2 = _LspEstado()
    st2.intentos_fallidos = 1
    rt._lsp["go"] = st2

    rt.reciclar_lsp()
    assert rt._lsp == {}
    assert viva._cerrada is True
