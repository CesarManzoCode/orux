"""Eviction de TeamRuntime ociosos.

Antes, `SyncServer._runtimes` crecía sin techo: cada equipo que se conectó
alguna vez retenía RAM (workspace + ownership + presencia + propuestas)
hasta que el proceso muriera. Sumado a la pared económica del host, en un
par de meses con tracción real era OOM.

Reglas que estos tests blindan:
- Sin conexiones + TTL pasado → se evicta.
- Con conexiones activas → NO se evicta (aunque el TTL sea cero).
- Con propuestas pendientes y SIN proposals_store → NO se evicta (perder
  propuestas no es aceptable en modo dev).
- Con propuestas pendientes y CON proposals_store → SÍ se evicta; al
  volver se rehidrata vía el flujo normal de `_runtime_para`.
- Locks (`_rt_locks`, `_asientos_locks`) se limpian al evictar.

Se ejercita a nivel de unidad (sin WebSocket): el barrido es lógica pura
sobre el dict de runtimes; el flujo de WebSocket ya está cubierto por la
suite existente y el setting de `_vacio_desde` lo hace `_sesion_equipo`.
"""

from __future__ import annotations

import time

import pytest

from orux.server.sync import SyncServer
from orux.state import MemProposalsStore


pytestmark = pytest.mark.asyncio


async def test_runtime_vacio_y_ttl_pasado_se_evicta() -> None:
    srv = SyncServer()
    rt = await srv._runtime_para("eq1")
    # Recién creado: arranca con _vacio_desde marcado. Forzamos un tiempo
    # remoto en el pasado para simular TTL cumplido.
    rt._vacio_desde = time.monotonic() - 9999

    assert "eq1" in srv._runtimes
    assert await srv._evictar_runtime("eq1") is True
    assert "eq1" not in srv._runtimes
    assert "eq1" not in srv._rt_locks


async def test_runtime_con_clientes_no_es_evictable() -> None:
    srv = SyncServer()
    rt = await srv._runtime_para("eq1")
    rt.clients.add(object())  # simula una conexión viva
    rt._vacio_desde = None  # alguien adentro
    assert srv._runtime_evictable(rt, ttl=0, ahora=time.monotonic()) is False


async def test_runtime_recien_vacio_no_se_evicta_si_ttl_no_paso() -> None:
    srv = SyncServer()
    rt = await srv._runtime_para("eq1")
    # _vacio_desde fresco, TTL largo: no es candidato.
    rt._vacio_desde = time.monotonic()
    assert srv._runtime_evictable(rt, ttl=3600, ahora=time.monotonic()) is False


async def test_runtime_con_propuestas_sin_store_no_se_evicta() -> None:
    """Sin proposals_store, evictar perdería propuestas. Defensa explícita:
    en modo dev preferimos retener RAM antes que perder estado de usuario."""
    srv = SyncServer()  # sin proposals_store
    rt = await srv._runtime_para("eq1")
    rt._vacio_desde = time.monotonic() - 9999  # ocioso eterno
    rt.proposals.put(
        path="x", author_id="b", author_name="B", content="hola",
    )
    assert srv._runtime_evictable(
        rt, ttl=60, ahora=time.monotonic(),
    ) is False


async def test_runtime_con_propuestas_y_store_se_evicta_y_rehidrata() -> None:
    """Con store de persistencia, evictar es seguro: al volver, el runtime
    se rehidrata con las mismas propuestas."""
    store = MemProposalsStore()
    srv = SyncServer(proposals_store=store)
    rt = await srv._runtime_para("eq1")
    rt._vacio_desde = time.monotonic() - 9999

    prop = rt.proposals.put(
        path="x", author_id="b", author_name="B", content="vivo",
    )
    await srv._persistir_prop(rt, prop)

    assert srv._runtime_evictable(
        rt, ttl=60, ahora=time.monotonic(),
    ) is True
    assert await srv._evictar_runtime("eq1") is True
    assert "eq1" not in srv._runtimes

    # Al volver alguien: el runtime nuevo trae la propuesta del store.
    rt2 = await srv._runtime_para("eq1")
    assert rt2 is not rt  # objeto nuevo
    rehidratada = rt2.proposals.get(prop.id)
    assert rehidratada is not None
    assert rehidratada.content == "vivo"


async def test_runtime_no_evicta_si_git_lock_tomado() -> None:
    """Trabajo en vuelo no debe perderse a mitad. Si git está corriendo
    (commit/push/clone) no evictamos aunque clients esté vacío."""
    srv = SyncServer()
    rt = await srv._runtime_para("eq1")
    rt._vacio_desde = time.monotonic() - 9999

    await rt._git_lock.acquire()
    try:
        assert srv._runtime_evictable(
            rt, ttl=60, ahora=time.monotonic(),
        ) is False
    finally:
        rt._git_lock.release()


async def test_runtime_no_evicta_si_estado_lock_tomado() -> None:
    srv = SyncServer()
    rt = await srv._runtime_para("eq1")
    rt._vacio_desde = time.monotonic() - 9999

    await rt._estado_lock.acquire()
    try:
        assert srv._runtime_evictable(
            rt, ttl=60, ahora=time.monotonic(),
        ) is False
    finally:
        rt._estado_lock.release()


async def test_evictar_runtime_inexistente_no_rompe() -> None:
    """No-op defensivo: evictar un team_id que no existe (otra corutina
    ya lo evictó, o nunca existió) retorna False y sigue."""
    srv = SyncServer()
    assert await srv._evictar_runtime("nunca-existio") is False


async def test_evictar_runtime_limpia_asientos_lock() -> None:
    srv = SyncServer()
    await srv._runtime_para("eq1")
    # Simulamos que la tarea de ajuste de asientos creó su lock.
    import asyncio
    srv._asientos_locks["eq1"] = asyncio.Lock()

    rt = srv._runtimes["eq1"]
    rt._vacio_desde = time.monotonic() - 9999
    assert await srv._evictar_runtime("eq1") is True
    assert "eq1" not in srv._asientos_locks


async def test_runtime_creado_arranca_marcado_como_vacio() -> None:
    """Sin esto, un runtime creado nunca se podría evictar (siempre
    _vacio_desde=None hasta que entre y salga alguien)."""
    srv = SyncServer()
    rt = await srv._runtime_para("eq1")
    assert rt._vacio_desde is not None
