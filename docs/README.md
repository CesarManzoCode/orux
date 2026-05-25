# Documentación del backend de Orux

Este directorio documenta cómo está construido el backend del producto. La fuente de verdad es siempre el código (`backend/orux/`); este árbol es la guía para entrar a ese código y entender las decisiones que ya se tomaron.

Si llegaste recién: empezá por [`architecture/overview.md`](architecture/overview.md) — explica los pilares (hexagonal puro, dominio puro, ports & adapters) en ~10 minutos de lectura.

## Estructura de la documentación

| Carpeta | Qué encontrás |
|---|---|
| [`architecture/`](architecture/) | Cómo está organizado el backend (hex 100%): dominio, application, ports, adapters, composition root. |
| [`domain/`](domain/) | El dominio puro: state (workspace/ownership/proposals), identity, plans, protocol, billing, analysis, teams. |
| [`application/`](application/) | Los use cases que orquestan el dominio + adapters. |
| [`adapters/`](adapters/) | Las implementaciones concretas: Postgres, JSON local, Git, Stripe, LSP, WebSocket, HTTP. |
| [`flows/`](flows/) | Recorridos end-to-end: auth, edición coordinada, save+impacto, rename, git, billing. |
| [`security/`](security/) | Modelo de amenazas y mitigaciones: tokens, OAuth, paths, git, webhooks. |
| [`operations/`](operations/) | Deploy, backup, runbook, troubleshooting, variables de entorno. |
| [`development/`](development/) | Cómo correr local, tests, convenciones, agregar features. |

## Documentos sueltos pre-existentes

| Archivo | Para qué |
|---|---|
| [`smoke-test.md`](smoke-test.md) | Guion manual de 30-60 min para verificar el sistema tras cambios grandes. Ya ejecutado pre-anuncio; se re-corre si toca algo crítico. |
| [`housekeeping-pre-anuncio.md`](housekeeping-pre-anuncio.md) | Checklist operativa en el VPS antes de invitar tráfico (limpieza de testing data, healthchecks, etc.). |
| [`oauth-github.md`](oauth-github.md) | Setup detallado del OAuth con GitHub (env vars, redirect URI, etc.). |

## Tres atajos según para qué viniste

- **"Quiero entender qué hace el sistema"** → [`architecture/overview.md`](architecture/overview.md) + [`flows/`](flows/).
- **"Quiero tocar el código"** → [`development/setup.md`](development/setup.md) + [`development/adding-feature.md`](development/adding-feature.md) + el módulo específico en [`domain/`](domain/) o [`adapters/`](adapters/).
- **"Tengo que operar el VPS"** → [`operations/runbook.md`](operations/runbook.md) + [`operations/troubleshooting.md`](operations/troubleshooting.md) + el `RUNBOOK.md` de la raíz del repo.

## Convenciones

- **Idioma**: todo en español.
- **Code-as-truth**: los docs envejecen; ante una duda, abrir el archivo del código mencionado (los docs siempre apuntan a paths concretos: `backend/orux/.../X.py`).
- **Decisiones documentadas**: cada decisión no obvia tiene un *por qué* explícito (no solo *qué*). Si encontrás algo "qué hace" sin "por qué", probablemente hay una decisión perdida — vale la pena preguntar.
- **Por capas, no por features**: el código se construyó por capas (1 a 33+); cada capa es real-pero-mínima. Esta documentación se organiza por *componentes* (hex) en vez de por *capas* (cronología) porque para un dev nuevo es más útil.

## Estado del refactor hex

El backend está organizado físicamente según hexagonal puro desde **2026-05-24**:

```
backend/orux/
├── domain/         puro: state, identity, plans, protocol, billing, analysis, teams
├── application/    use cases (orquestación)
├── ports/          11 Protocols formales
├── adapters/
│   ├── inbound/{websocket,http}/
│   └── outbound/{json,identity,billing,analysis,postgres,git}/
├── composition.py  build_server(config)
└── [paths viejos como state/, server/, api/, etc.: re-exports backward-compat]
```

**513 tests verdes** en la suite (`cd backend && python -m pytest -q`). Ver [`architecture/overview.md`](architecture/overview.md) para el detalle.
