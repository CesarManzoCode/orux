# Development: Testing

**513 tests** en `backend/tests/`. Suite corre en ~23s sin Postgres, ~30s con marcadores `slow`.

## Comandos

```bash
cd backend

# Suite completa
python -m pytest -q

# Detiene en el primer fallo
python -m pytest -x -q

# Solo un archivo
python -m pytest tests/test_sync.py -v

# Solo un test
python -m pytest tests/test_sync.py::test_update_aplica_sin_dueno -v

# Por marcador
python -m pytest -m slow      # solo lentos (LSP real)
python -m pytest -m "not slow"  # rápidos

# Con cobertura
python -m pytest --cov=orux --cov-report=term-missing
```

## Configuración

`pyproject.toml` setea:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"   # async def test_* corren como async automático
```

## Fixtures principales

### `conftest.py` global

```python
@pytest_asyncio.fixture
async def sync_server():
    """SyncServer en memoria, sin Postgres, sin auth real."""
    server = SyncServer()
    ws = await serve(server.handle, "localhost", 0)
    port = ws.sockets[0].getsockname()[1]
    try:
        yield server, port
    finally:
        ws.close()
        await ws.wait_closed()
```

Levanta un server real en puerto efímero. Los tests se conectan con `websockets.connect`.

### `tmp_path` (built-in de pytest)

Directorio temporal único por test. Lo usan los tests que tocan disco (`DiskStorage`, `JsonOwnershipStore`, `JsonUserStore`).

## Estructura por archivo

| Archivo | Cubre |
|---|---|
| `test_protocol.py` | Codec + validación de mensajes |
| `test_workspace.py` | Workspace + topes + delete |
| `test_storage.py` | DiskStorage + atomic write + paths inseguros |
| `test_proposals_persistencia.py` | Proposals persistencia con ProposalsStorePort |
| `test_presence.py` | Roster + color determinista |
| `test_locks.py` | `lineas_tocadas` (LCS + truncado) |
| `test_identity.py` | UserStore + passwords + tokens |
| `test_oauth.py` | OAuth GitHub funciones puras |
| `test_admin.py` | UserStore.admin() + Ownership.asignar() |
| `test_admin_audit.py` | Logging contextual del admin |
| `test_teams.py` | MemTeamStore + validaciones + invitaciones |
| `test_billing.py` | Stripe funciones puras |
| `test_plans.py` | Planes + límites + helpers |
| `test_analysis.py` | Tiers + impacto (Python AST) |
| `test_analysis_js.py` | tree-sitter JS/TS |
| `test_analysis_go_rust.py` | tree-sitter Go + Rust |
| `test_analysis_tiers.py` | Jerarquía de tiers |
| `test_transitive.py` | Impacto transitivo (premium) |
| `test_rename.py` | Detección + codemod de rename |
| `test_lsp.py` | LSP real (marker `slow`) |
| `test_lsp_retry.py` | Cooldown exponencial del LSP |
| `test_git.py` | GitRepo + URL allowlist + scrubbing |
| `test_robustez.py` | Path inseguro + atomic writes + topes |
| `test_robustez_extras.py` | Re-exports compat + eviction de runtimes |
| `test_sync.py` | Integración end-to-end del SyncServer |
| `test_runtime_eviction.py` | Eviction de TeamRuntime ociosos |
| `test_api_service.py` | Use cases HTTP (login_operador, listar_*, etc.) |
| `test_ports_contract.py` | Cada adapter cumple su Port (isinstance) |

## Convenciones

### Naming

- `test_<lo_que_cubre>` para tests sync.
- `async def test_<lo_que_cubre>` para tests async (corren automático por `asyncio_mode=auto`).
- Si testeas un caso negativo, ser explícito: `test_X_no_aplica_si_Y`, `test_path_inseguro_no_entra_al_estado`.

### Sin mocks pesados

La regla del proyecto: **integración real, no mocks**. Razones:

- Los Mem* (`MemTeamStore`, `MemProposalsStore`, `MemWebhooksStore`) son la implementación de referencia. Cumplen el Port igual que los Pg*. Tests usan Mem; producción usa Pg.
- Levantar un `SyncServer` real en puerto efímero por test es rápido (~10ms).
- Mockear es frágil: cambias el método del dominio y el test sigue pasando con el mock falso.

Excepciones donde sí mockeamos (4 archivos del total):

- `test_lsp.py`: mockea `SesionLSP` con un dummy que implementa `disponible`/`cerrar` cuando no es estrictamente sobre LSP.
- `test_lsp_retry.py`: monkey-patchea `arrancar_lsp` para simular fallos.
- `test_robustez_extras.py`: monkey-patchea `runtime_evictable` para probar robustez de la eviction.
- `test_billing.py`: usa `MemWebhooksStore` (que es el adapter en memoria del WebhooksStorePort, no un mock).

### Marcadores

```python
@pytest.mark.slow  # tests lentos (LSP real, retries con backoff)
@pytest.mark.integration  # tests que levantan un server real
```

Para skipear los lentos en dev rápido:

```bash
python -m pytest -m "not slow"
```

### Async helpers

```python
async def _entrar(ws, user="dev"):
    """auth + crear equipo + consumir handshake. Un cliente, server fresco."""
    await ws.send(json.dumps({"type": "register", "username": user, "password": "passw0rd"}))
    assert json.loads(await ws.recv())["type"] == "auth_ok"
    assert json.loads(await ws.recv())["type"] == "lobby"
    await ws.send(json.dumps({"type": "create_team", "nombre": "eq"}))
    assert json.loads(await ws.recv())["type"] == "team_ready"
    for esperado in ("init", "welcome", "ownership", "admin_info"):
        assert json.loads(await ws.recv())["type"] == esperado
```

Helpers como este viven en cada test file (o en `conftest.py` si se reusan). NO hay fixtures globales pesadas — preferimos código explícito.

### Trampas con re-exports y monkey-patches

Tras el refactor hex (2026-05-24), los re-exports backward-compat COPIAN atributos, no enlazan:

```python
# ✗ NO funciona — el binding interno del módulo real no cambia:
import orux.server.runtime as rmod
rmod.arrancar_lsp = fake_arrancar
res = rt.lsp_sesion("py")  # sigue usando el real

# ✓ Apuntar al módulo real:
import orux.adapters.inbound.websocket.runtime as rmod
rmod.arrancar_lsp = fake_arrancar
res = rt.lsp_sesion("py")  # ahora sí usa el fake
```

Casos arreglados en sesión 3 del refactor: `test_lsp_retry.py:155`, `test_robustez_extras.py:212`.

## Contract tests

`tests/test_ports_contract.py` verifica que cada adapter cumple su Port estructuralmente:

```python
def test_pg_ownership_cumple_port(db_dummy):
    assert isinstance(PgOwnershipStore(db_dummy), OwnershipStorePort)
```

16 tests, uno por (adapter, Port). Si renombrás un método del Port y olvidás el adapter, este test falla con `isinstance returned False` (claro y específico).

## Cobertura

```bash
python -m pytest --cov=orux --cov-report=term-missing
```

Cobertura actual: ~85%+ del código (excluyendo cáscaras HTTP que se prueban en el VPS).

Lo que NO cubrimos en sandbox:

- Llamadas reales a GitHub OAuth (`_intercambiar`): se prueba en el VPS.
- Llamadas reales a Stripe (`crear_sesion_checkout`, `actualizar_cantidad`): idem.
- LSP con resolución real (sí se cubre con `pyright` instalado y marker `slow`).
- asyncpg real (los stores se cubren con `_DbDummy` para isinstance; la integración real con la DB se prueba en VPS).

## CI

Hoy NO hay CI (etapa de prototipo, deploy manual). La suite se corre localmente antes de cada commit relevante.

Para agregar CI con GitHub Actions:

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: cd backend && pip install -e ".[dev]"
      - run: cd backend && python -m pytest -q
```

Diferido hasta que el equipo crezca o haya colaboradores externos.

## Performance de tests

El test más lento del suite es `test_lsp.py` (~5s por arrancar pyright real). Los demás son <100ms cada uno.

Para identificar tests lentos:

```bash
python -m pytest --durations=20
```

Si algún test se vuelve >1s sin razón clara, investigar (probablemente IO que se podría mock-fixturizar).

## Escribir un test nuevo

Pattern: arrange + act + assert.

```python
async def test_claim_aplica_si_libre(sync_server):
    server, port = sync_server
    async with connect(f"ws://localhost:{port}") as ws:
        await _entrar(ws, user="ana")
        # arrange: archivo nuevo (claim implícito por update)
        await ws.send(json.dumps({"type": "update", "path": "x.py", "content": "x = 1"}))
        # consumir broadcasts
        for _ in range(2):  # update + ownership
            await ws.recv()
        # act: explicit claim sobre otro path
        await ws.send(json.dumps({"type": "claim", "path": "y.py"}))
        # assert
        msg = json.loads(await ws.recv())
        assert msg["type"] == "ownership"
        assert msg["owners"]["y.py"] == "ana"
```

Para tests de funciones puras (sin server), simplemente:

```python
def test_path_seguro_rechaza_absoluto():
    assert path_seguro("/etc/passwd") is False
    assert path_seguro("C:\\Windows") is False
```

## Diagnosticar un test que falla

```bash
python -m pytest tests/test_sync.py::test_X -v -s
```

`-v`: verbose. `-s`: muestra prints/logs (sin capturarlos).

Para ver logs del server durante el test:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

al inicio del test (o agregar `--log-cli-level=DEBUG` a pytest).

## Tests que NO se ejecutan en sandbox

- Algunos test de `test_lsp.py` requieren `pyright-python-langserver` en PATH. Si no está: se saltean con razón clara.
- Algunos test de `test_git.py` requieren `git` binario. Si no está: se saltean.
- Cero tests requieren acceso a internet.

Si en algún momento un test requiere algo externo (DB, red), agregarlo bajo `@pytest.mark.integration` o `@pytest.mark.slow` y documentarlo aquí.

### Al revés: tests que fallan cuando el toolchain SÍ está

Un puñado de tests de `test_analysis_*.py` y `test_lsp_retry.py` afirman el
comportamiento **degradado** del sandbox: que `tier_para("main.go")` cae a regex
(nivel 3) porque no hay grammar de tree-sitter, o que `lsp_sesion("py")` devuelve
`None` porque no hay pyright en el PATH. Sus docstrings lo dicen ("en el sandbox
sin pyright…").

En una máquina donde `pip install -e ".[dev]"` sí trajo las grammars y pyright
arrancó, esos tests **fallan** — no porque el producto esté roto, sino porque su
precondición ya no se cumple. Es la trampa de un test que infiere su propio
entorno en vez de exigirlo. Si algún día se retoman, la forma correcta es
saltearlos explícitamente cuando el tier profundo está disponible, no afirmar el
tier bajo.
