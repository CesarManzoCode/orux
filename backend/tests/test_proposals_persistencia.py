"""Persistencia de propuestas cross-restart.

Antes vivían sólo en memoria del `TeamRuntime`: un deploy a mitad de "Ana
editó, Kai por aprobar" perdía el estado. Estos tests blindan que (a) el
SyncServer escribe-a-través el store en cada mutación, (b) un nuevo
`TeamRuntime` rehidrata desde el store, (c) las eliminaciones (resolve,
delete, clone destructivo) también se propagan al store.

Se ejercita con `MemProposalsStore` (sin Postgres). El contrato async es
idéntico a `PgProposalsStore`; lo que falla acá fallaría allá igual.
"""

from __future__ import annotations

import pytest

from orux.protocol import Proposal
from orux.server.sync import SyncServer
from orux.state import MemProposalsStore


pytestmark = pytest.mark.asyncio


async def test_propuesta_se_escribe_al_store_y_rehidrata_en_restart():
    """El caso central: el server reinicia con propuestas pendientes y
    al volver a abrir el equipo, las propuestas siguen estando."""
    store = MemProposalsStore()

    # --- Instancia 1: alguien propone, el store la guarda ---
    srv1 = SyncServer(proposals_store=store)
    rt1 = await srv1._runtime_para("eq1")
    prop = rt1.proposals.put(
        path="main.py", author_id="beto",
        author_name="Beto", content="hola desde beto",
    )
    await srv1._persistir_prop(rt1, prop)

    # El store la tiene
    guardadas = await store.cargar("eq1")
    assert len(guardadas) == 1
    assert guardadas[0].content == "hola desde beto"

    # --- Instancia 2: restart. NUEVO server con el MISMO store ---
    srv2 = SyncServer(proposals_store=store)
    rt2 = await srv2._runtime_para("eq1")

    # La propuesta vuelve al dict en memoria del nuevo runtime
    rehidratada = rt2.proposals.get(prop.id)
    assert rehidratada is not None
    assert rehidratada.path == "main.py"
    assert rehidratada.author_id == "beto"
    assert rehidratada.content == "hola desde beto"


async def test_resolve_borra_la_propuesta_del_store():
    store = MemProposalsStore()
    srv = SyncServer(proposals_store=store)
    rt = await srv._runtime_para("eq1")
    prop = rt.proposals.put(
        path="main.py", author_id="beto",
        author_name="Beto", content="x",
    )
    await srv._persistir_prop(rt, prop)
    assert len(await store.cargar("eq1")) == 1

    rt.proposals.pop(prop.id)
    await srv._borrar_prop(rt, prop.id)
    assert await store.cargar("eq1") == []


async def test_delete_path_borra_propuestas_del_store():
    """Cuando se borra el archivo, todas las propuestas sobre ese path
    quedan moot — el store también las pierde."""
    store = MemProposalsStore()
    srv = SyncServer(proposals_store=store)
    rt = await srv._runtime_para("eq1")
    p1 = rt.proposals.put(
        path="main.py", author_id="b", author_name="B", content="x",
    )
    p2 = rt.proposals.put(
        path="main.py", author_id="c", author_name="C", content="y",
    )
    p3 = rt.proposals.put(
        path="otro.py", author_id="b", author_name="B", content="z",
    )
    for p in (p1, p2, p3):
        await srv._persistir_prop(rt, p)
    assert len(await store.cargar("eq1")) == 3

    rt.proposals.drop_path("main.py")
    await srv._borrar_props_path(rt, "main.py")
    quedan = await store.cargar("eq1")
    assert [p.id for p in quedan] == [p3.id]


async def test_clone_destructivo_limpia_todas_las_propuestas_del_store():
    """`_reiniciar_para_todos` (tras un clone destructivo) tira el set
    entero de propuestas: el workspace es OTRO repo y las propuestas
    viejas ya no aplican."""
    store = MemProposalsStore()
    srv = SyncServer(proposals_store=store)
    rt = await srv._runtime_para("eq1")
    p1 = rt.proposals.put(
        path="a", author_id="b", author_name="B", content="x",
    )
    p2 = rt.proposals.put(
        path="b", author_id="c", author_name="C", content="y",
    )
    for p in (p1, p2):
        await srv._persistir_prop(rt, p)

    await srv._borrar_props_todo(rt)
    assert await store.cargar("eq1") == []


async def test_propuestas_son_por_equipo_no_se_mezclan():
    """Equipos distintos no comparten propuestas — aislamiento garantizado
    a nivel de store, no sólo en memoria del runtime."""
    store = MemProposalsStore()
    srv = SyncServer(proposals_store=store)
    rt1 = await srv._runtime_para("eq1")
    rt2 = await srv._runtime_para("eq2")

    p1 = rt1.proposals.put(
        path="x", author_id="b", author_name="B", content="del eq1",
    )
    p2 = rt2.proposals.put(
        path="x", author_id="b", author_name="B", content="del eq2",
    )
    await srv._persistir_prop(rt1, p1)
    await srv._persistir_prop(rt2, p2)

    eq1 = await store.cargar("eq1")
    eq2 = await store.cargar("eq2")
    assert len(eq1) == 1 and eq1[0].content == "del eq1"
    assert len(eq2) == 1 and eq2[0].content == "del eq2"


async def test_reedicion_misma_propuesta_reemplaza_no_acumula():
    """Si el autor reedita el mismo path, la propuesta vieja se reemplaza
    en memoria (id determinista) Y en el store (UPSERT)."""
    store = MemProposalsStore()
    srv = SyncServer(proposals_store=store)
    rt = await srv._runtime_para("eq1")

    p1 = rt.proposals.put(
        path="main.py", author_id="b",
        author_name="B", content="versión 1",
    )
    await srv._persistir_prop(rt, p1)
    p2 = rt.proposals.put(
        path="main.py", author_id="b",
        author_name="B", content="versión 2",
    )
    await srv._persistir_prop(rt, p2)

    guardadas = await store.cargar("eq1")
    assert len(guardadas) == 1  # reemplazo, no acumulación
    assert guardadas[0].content == "versión 2"
    assert p1.id == p2.id  # id determinista path::author


async def test_sin_proposals_store_no_rompe_nada():
    """Modo dev (sin DB): los helpers son no-ops, el flujo funciona igual.
    Compat estricta con la firma anterior."""
    srv = SyncServer()  # sin proposals_store
    rt = await srv._runtime_para("eq1")
    prop = rt.proposals.put(
        path="x", author_id="b", author_name="B", content="x",
    )
    await srv._persistir_prop(rt, prop)
    await srv._borrar_prop(rt, prop.id)
    await srv._borrar_props_path(rt, "x")
    await srv._borrar_props_todo(rt)


async def test_cargar_hidrata_indice_por_autor():
    """Tras la rehidratación, `drop_author` debe seguir funcionando — eso
    valida que el índice secundario por autor se reconstruyó al `cargar`,
    no sólo el dict principal."""
    store = MemProposalsStore()

    srv1 = SyncServer(proposals_store=store)
    rt1 = await srv1._runtime_para("eq1")
    p1 = rt1.proposals.put(
        path="a", author_id="beto", author_name="Beto", content="x",
    )
    p2 = rt1.proposals.put(
        path="b", author_id="beto", author_name="Beto", content="y",
    )
    p3 = rt1.proposals.put(
        path="a", author_id="ana", author_name="Ana", content="z",
    )
    for p in (p1, p2, p3):
        await srv1._persistir_prop(rt1, p)

    # Restart
    srv2 = SyncServer(proposals_store=store)
    rt2 = await srv2._runtime_para("eq1")

    rt2.proposals.drop_author("beto")
    assert rt2.proposals.get(p1.id) is None
    assert rt2.proposals.get(p2.id) is None
    assert rt2.proposals.get(p3.id) is not None  # ana sigue
