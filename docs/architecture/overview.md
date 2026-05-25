# Arquitectura del backend: hexagonal puro

Este documento explica los pilares de cómo está organizado el backend. Si solo vas a leer un documento, leé éste.

## Qué construimos

Un editor colaborativo en tiempo real sobre Git. Capa de coordinación que previene colisiones, detecta impacto semántico de cambios automáticamente, y distribuye el conocimiento del proyecto.

La tesis no negociable: **misma seguridad que el flujo actual (branches, PRs, reviews, merges), sin la ceremonia. El sistema sabe sin que nadie le pregunte.**

## Tres reglas que ordenan todo el código

1. **El dominio no sabe que existe Postgres, ni WebSockets, ni Stripe.** El dominio modela "qué es un workspace, qué es ownership, qué reglas tiene una propuesta". Lo escribiría exactamente igual si en lugar de Postgres usáramos SQLite, o si en lugar de WebSockets hablara por Signal.

2. **Los efectos externos pasan siempre por un Port (contrato formal).** Si una pieza del sistema necesita persistir algo, no llama a Postgres ni a un archivo JSON: llama a `OwnershipStorePort.guardar(...)`. Quien decide qué hay detrás del Port (Postgres en producción, JSON en dev, in-memory en tests) es el composition root, no el caller.

3. **La orquestación vive en use cases, no en handlers.** Un mensaje WebSocket no sabe cómo se hace ownership; solo decodifica el mensaje, llama a `claim_use_case(...)`, y traduce el resultado a un broadcast.

Estas tres reglas son lo que un libro llamaría "hexagonal puro". El término no importa; las reglas sí.

## Layout físico

```
backend/orux/
├── domain/         puro: state, identity, plans, protocol, billing, analysis, teams
├── application/    use cases (orquestación) — depende de domain + ports
├── ports/          contratos formales (Protocols)
├── adapters/
│   ├── inbound/    quien INICIA conversaciones con el dominio
│   │   ├── websocket/  SyncServer + dispatch (lo que los devs usan)
│   │   └── http/       app.py (panel admin, OAuth callback, webhook Stripe)
│   └── outbound/   adapters concretos para los Ports
│       ├── json/       JSON local (modo dev sin DB)
│       ├── identity/   HMAC tokens + OAuth GitHub
│       ├── billing/    Stripe
│       ├── analysis/   wrapper sobre el motor de análisis
│       ├── postgres/   asyncpg + Pg*Stores
│       └── git/        binario `git` con endurecimiento
├── composition.py  único lugar que cablea ports ↔ adapters
└── [paths viejos: state/, identity/, server/, api/, db/, git/, … son re-exports backward-compat tras el refactor del 2026-05-24]
```

## Flujo de dependencias (la regla de oro)

Las flechas indican qué importa qué; **nunca al revés**:

```
adapters/inbound  →  application  →  domain
                            ↓
                          ports  ←  adapters/outbound
```

Concretamente:

- **`domain/` importa solo de `domain/`** (más algunas utilities cross-cutting en `orux/_env.py` y `orux/_net.py`). Cero imports a `adapters/`, `application/` ni `ports/`.
- **`application/` importa de `domain/` y `ports/`.** No importa adapters concretos.
- **`adapters/outbound/` implementa Protocols de `ports/`.** Puede importar de `domain/` para usar value objects (`Proposal`, `EstadoGit`).
- **`adapters/inbound/` traduce protocolo externo ↔ use cases.** Importa de `application/` (use cases) y `domain/` (validación local). Puede importar adapters concretos solo en el caso de `runtime.py` (la sesión LSP del equipo).
- **`composition.py` importa de todos lados** — es el único lugar donde se decide qué adapter usar para cada Port. Lo cablea el `__main__`.

## Los Ports (contratos formales)

Hay 11 Ports definidos en `backend/orux/ports/`. Cada uno es un `typing.Protocol` con `@runtime_checkable` para que se pueda validar estructuralmente con `isinstance`.

| Port | Para qué | Implementaciones |
|---|---|---|
| `WorkspaceStoragePort` | Persistir archivos del workspace en disco (sync por el hot path) | `DiskStorage` |
| `OwnershipStorePort` | Cargar/guardar el mapa ownership por equipo | `JsonOwnershipStore` (dev), `PgOwnershipStore` (prod) |
| `ProposalsStorePort` | Persistir propuestas tentativas por equipo | `MemProposalsStore`, `PgProposalsStore` |
| `UserStorePort` | Persistir usuarios (identidad) | `JsonUserStore` (dev), `PgUserStore` (prod) |
| `WebhooksStorePort` | Idempotencia de webhooks de Stripe por event_id | `MemWebhooksStore`, `PgWebhooksStore` |
| `TeamStorePort` | Equipos, membresía, invitaciones | `MemTeamStore` (dev/tests), `PgTeamStore` (prod) |
| `GitPort` | Operaciones git sobre el workspace de un equipo | `GitRepo` (alias `GitBinaryAdapter`) |
| `SessionTokenPort` | Emitir/verificar tokens de sesión HMAC | `HmacSessionTokenAdapter` |
| `OAuthPort` | Flujo OAuth GitHub (URL, state CSRF, identidad) | `GithubOAuthAdapter` |
| `BillingPort` | Operaciones del proveedor de pagos | `StripeBillingAdapter` |
| `AnalysisPort` + `LspFactoryPort` + `LspSession` | Análisis semántico + sesiones LSP | `SemanticAnalysisAdapter`, `LspFactoryAdapter` |

Cada Port se verifica con un *contract test* (`backend/tests/test_ports_contract.py`): si alguien renombra un método del Port y se olvida del adapter, este test falla con un mensaje claro en vez de un `AttributeError` en runtime.

## El application layer (use cases)

Cada handler de mensaje del WS o request HTTP se traduce a un *use case* en `backend/orux/application/`:

- `update_use_case`, `claim_use_case`, `delete_use_case`, `resolve_use_case`, `admin_assign_use_case`, `admin_assign_many_use_case`, `create_invite_use_case`, `presence_use_case`, `commit_use_case`, `clone_use_case`, `push_use_case` (todos en `use_cases.py`).
- `calcular_impacto_save`, `calcular_propagar_rename` (en `impacto.py`) — la lógica del checkpoint Ctrl+S y el codemod de rename premium.
- `login_operador`, `listar_usuarios`, `listar_teams`, `aplicar_evento_stripe`, etc. (en `http_use_cases.py`) — los use cases del panel del operador.

Cada use case recibe:
- el `TeamRuntime` (estado vivo del equipo: workspace, ownership, proposals, roster);
- los Ports que necesita (inyectados desde el caller);
- un `Command` (dataclass con los datos de entrada);

…y devuelve un `Result` (dataclass con los efectos que el inbound debe publicar). El inbound del WS traduce esos efectos a `_broadcast` / `_enviar_a` / `encode`; el inbound HTTP los traduce a JSONResponse.

Esto es lo que hace que **un cambio de protocolo (WS → SSE, por ejemplo) NO requiera tocar los use cases**, y que **un cambio en la lógica de negocio NO requiera tocar el transporte**.

## El composition root

`backend/orux/composition.py:build_server(config)` es el único lugar donde se decide qué adapter usar para cada Port. Recibe un `AppConfig` (toda la config externa: DSN, secrets, paths) y devuelve un `SyncServer` listo para correr.

Dos modos:

- **Con DSN** (producción): `PgUserStore`, `PgTeamStore`, `PgOwnershipStore`, `PgProposalsStore`; el workspace de cada equipo es su propio repo git en `base_dir/ws/<team_id>/`.
- **Sin DSN** (dev): `JsonUserStore`, `JsonOwnershipStore`; workspace único en `base_dir/workspace/`.

`__main__.py` se reduce a: cargar config, llamar composition, registrar handlers de señales.

## Por qué hex (la pregunta razonable)

El producto **no** estaba en deuda por no ser hex. Funcionaba. La elección de migrar fue del usuario, post-anuncio, con tiempo libre y Claude Max — el cálculo era "ya que está estable y desplegado, dejarlo arquitectónicamente sólido para mantenimiento futuro".

Lo que ganamos:

1. **Cambiar persistencia es 1 línea en composition.py.** El día que entre SQLite local, Redis para sessions, o un segundo backend de billing, ya hay un Port para enchufar.
2. **Tests sin DB.** Los `Mem*Store` cumplen los mismos Ports que los `Pg*Store`; los tests son rapidísimos (`pytest -q` en ~23s para 513 tests).
3. **Reorganizar lógica sin tocar transporte.** Los use cases son funciones puras (modulo el side-effect del runtime); refactorearlos es seguro.
4. **El dominio se mantiene legible.** No tiene `asyncpg`, ni `subprocess`, ni `urllib` mezclados.

Lo que NO ganamos:

- Performance. Hex es organizativo, no rinde más.
- Funcionalidad. El cliente no nota nada.
- Inmunidad a bugs. Si tenés un bug en la lógica, va a estar en `application/` o `domain/` — el lugar es más claro, pero el bug no se previene solo.

## Cosas a recordar

- **El código en `orux/state/`, `orux/server/`, `orux/api/`, etc. son re-exports backward-compat** del refactor del 2026-05-24. Funcionan, pero el código nuevo debe importar desde la ubicación real (`orux.domain.state`, `orux.adapters.inbound.websocket`, `orux.adapters.inbound.http`).
- **Trampa de monkey-patches con re-exports**: los re-exports copian atributos, no enlazan. Si un test hace `monkeypatch.setattr(orux.server.runtime, "arrancar_lsp", X)`, NO afecta al binding interno del módulo real. Patchear `orux.adapters.inbound.websocket.runtime` en su lugar.
- **`_env.py` y `_net.py` quedan en `orux/` raíz** como utilities cross-cutting (no son dominio ni adapter).
