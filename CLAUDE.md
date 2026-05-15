# Contexto del proyecto

Este directorio contiene el proyecto **laidea** (nombre temporal). El README.md tiene la visión completa. Léelo primero antes de hacer cualquier cosa.

## Qué estamos construyendo

Un editor colaborativo en tiempo real sobre Git para equipos de 2 a 50 devs. Capa de coordinación que previene colisiones, detecta impacto semántico de cambios automáticamente, y distribuye el conocimiento del proyecto para que el líder no sea el cuello de botella.

No reemplaza Git, GitHub, ni IDEs. No es Replit. No es governance corporativo.

## Tesis

> Misma seguridad que el flujo actual (branches, PRs, reviews, merges), sin la ceremonia. El sistema sabe sin que nadie le pregunte.

Lo que vendemos al dev: "Toca lo que necesites. El sistema se encarga de que nada se rompa."

Lo que NO vendemos: ownership, enforcement, permisos, control, vigilancia. El ownership es implementación interna (el diferencial del coche), no es lo que se vende.

## Estado actual

Fase muy temprana. La idea completa vive en `README.md`. Existen ya las **capas 1, 2, 3 y 4** implementadas como paquete Python instalable:

- `laidea/protocol/` — capa 1: `Init`, `Update`. Capa 2: `Welcome`, `Presence`, `Leave` + estado `PresenceState`. Capa 4: `ClaimMessage(path)`, `OwnershipMessage(owners)`, `ProposalMessage(proposal)` + estado `Proposal`, `ResolveMessage(proposal_id, accept)`. Encode/decode con `asdict`.
- `laidea/state/` — `Document`, `Workspace` (acepta storage opcional), `Roster` (presencia), `DiskStorage` (capa 3: valida paths contra traversal), `Ownership` (capa 4: path→client_id dueño; efímero, se libera al desconectar), `Proposals` (capa 4: id `path::author_id` determinista, sin cola para dueños offline).
- `laidea/server/` — `SyncServer(storage=None)`. Handshake de 3 mensajes: `init`→`welcome`→`ownership`. Update de no-dueño sobre archivo con dueño = propuesta al dueño (no se aplica/difunde). `resolve` aprobar = aplica + `_broadcast_todos` (incluye al dueño que aprobó); rechazar = revierte al autor. Solo el dueño actual resuelve. Al desconectar: libera ownership y descarta sus propuestas. `__main__` cablea `DiskStorage` real.
- `web/index.html` — sidebar con badges de presencia; marcas de línea sobre el textarea (`white-space: pre`, `line-height` 22px fijo; `LINE_H`/`PAD_TOP` en JS deben coincidir con CSS). Capa 4: chip de dueño + botón "reclamar", aviso al autor de cambio tentativo, bandeja del dueño con diff por líneas (LCS) y botones aprobar/rechazar.
- `tests/` — 54 tests. Contratos intactos: `init` primer mensaje, broadcasts de update SIEMPRE con `path`. `handshake()` en `test_sync.py` consume `init`+`welcome`+`ownership`. Storage/tests usan `tmp_path`.
- `pyproject.toml` — `pip install -e ".[dev]"`. Server: `python -m laidea.server` o `laidea-server`.

Presencia es por archivo + número de línea (no posición de caracter). Estar conectado ≠ estar presente. Persistencia: memoria primero/disco después; persistir nunca propaga excepción. Ownership (capa 4): andamiaje de prototipo — claim manual, identidad anónima por sesión, se libera al desconectar (para evitar deadlock sin auth); en el producto se asigna/infiere y persiste. Propuestas = archivo completo (per-línea es capa 5).

Capas pendientes (en orden): **capa 5 = prevención de colisiones + apply por-línea** (separada de capa 4 a propósito), después análisis semántico, notificaciones a owners, integración Git. CRDT real solo si un perfilador/uso lo justifica — la tesis es prevenir, no fusionar.

## Trampas operativas ya vistas

- **Servidor zombi en puerto 8765.** Al cambiar el protocolo, si un servidor de versión anterior sigue corriendo, los clientes nuevos hablan con él y aparecen archivos fantasma llamados "undefined" en la UI. Antes de debuggear lógica, verificar siempre: `ps aux | grep python | grep -v grep` y `lsof -i:8765`. El comando correcto para arrancar el server actual es `python -m laidea.server`, no `python server.py` (ese archivo ya no existe).

## Principios para colaborar en este proyecto

- **Idioma: español.** Toda comunicación, comentarios, mensajes de commit y artefactos en español.
- **Construcción por capas.** Orden estricto: estado compartido → edición en tiempo real → ownership → análisis semántico → notificaciones → integración Git. No se añade una capa hasta que la anterior funcione.
- **Cada capa: "real pero mínima".** Estructura y tests desde el primer commit. Nada de abstracciones para problemas que aún no existen. Si una capa empieza a requerir "ah pero también necesito X y Y", son dos capas, se separan.
- **Riesgo crítico identificado: feature soup.** Resistir proponer features extra. Una capa increíble vale más que veinte mediocres.
- **El núcleo es la coordinación semántica, no el editor.** El editor es vehículo.
- **Stack: Python.** Es el lenguaje principal del usuario. Para el realtime hot path se migrará selectivamente solo si un perfilador lo justifica.

## Decisiones ya tomadas

- Plataforma fase 1: web app.
- Plataforma fase 2: ir al entorno del dev (plugins de VSCode, JetBrains).
- Sobre Git: integración, no reemplazo. `git clone` debe bastar.
- Sin modo offline. Estado compartido en tiempo real es la base.
- Público objetivo inicial: equipos nuevos sin inercia, open source que empieza, founders técnicos 2-3 personas.
- Decisor de adopción: líder del equipo (CTO, tech lead, founder técnico).

## Qué falta definir (no decidir todavía sin que el usuario lo pida)

- Solución de CRDT (probable: `y-py`, los bindings de Python a Yrs). Se decide cuando lleguemos a la capa de CRDT real, no antes.
- Primer lenguaje a soportar para análisis semántico (probable: TypeScript).
- Modelo de negocio y pricing.
- Nombre real del producto.
- Cómo manejar autenticación / identidad de usuarios (necesario antes de presencia con nombre real, no antes de presencia anónima).

## Cómo se debe sentir el producto

- "Misma vida, menos dolor."
- Live collaborative review, no governance corporativo.
- Multiplayer semantic coding.
- El dev no se siente bloqueado antes de intentar.
- El owner no siente que invadieron su código.
- Editar primero. Negociar después. Aplicar al final.
