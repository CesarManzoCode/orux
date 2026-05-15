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

Fase muy temprana. La idea completa vive en `README.md`. Existen ya las **capas 1, 2, 3, 4 y 5** implementadas como paquete Python instalable:

- `laidea/protocol/` — capa 1: `Init`, `Update`. Capa 2: `Welcome`, `Presence`, `Leave` + estado `PresenceState`. Capa 4: `ClaimMessage(path)`, `OwnershipMessage(owners)`, `ProposalMessage(proposal)` + estado `Proposal`, `ResolveMessage(proposal_id, accept)`. Encode/decode con `asdict`.
- `laidea/state/` — `Document`, `Workspace` (storage opcional; `exists()` distingue crear de editar), `Roster` (presencia efímera + identidad estable por token: `asignar(token)`, `lineas_ocupadas()`), `DiskStorage` (capa 3), `Ownership` (capa 4: efímero, NO se libera al desconectar — sobrevive por token), `Proposals` (capa 4: id `path::author_id`), `lineas_tocadas` (capa 5: diff LCS, líneas del viejo que el nuevo borra/modifica; insertar NO toca las desplazadas).
- `laidea/server/` — `SyncServer(storage=None)`. Handshake de 3 mensajes: `init`→`welcome`→`ownership`. Crear archivo (primer update sobre path nuevo sin dueño) hace dueño al creador. Update de no-dueño sobre archivo con dueño = propuesta. Capa 5: si el archivo NO tiene dueño y el update pisa una línea ocupada por otro presente, se rechaza (se devuelve lo autoritativo al emisor, `continue`); el dueño no tiene lock. `resolve` aprobar = `_broadcast_todos`; rechazar = revierte al autor. Al desconectar: libera ownership, descarta sus propuestas. `__main__` cablea `DiskStorage`.
- `web/index.html` — sidebar con badges de presencia; marcas de línea sobre el textarea (`white-space: pre`, `line-height` 22px fijo; `LINE_H`/`PAD_TOP` en JS deben coincidir con CSS). Capa 4: chip de dueño + botón "reclamar", aviso al autor de cambio tentativo, bandeja del dueño con diff por líneas (LCS) y botones aprobar/rechazar.
- `tests/` — 72 tests. Contratos intactos: `init` primer mensaje, broadcasts de update SIEMPRE con `path`, nunca eco de update al emisor. `handshake()` consume `init`+`welcome`+`ownership`; `recv_tipo()` filtra el `ownership` que difunde crear archivos. Fixture `servidor` cede (SyncServer, port) para pre-sembrar workspace sin dueño. `test_locks.py`/`test_presence.py` prueban piezas puras. Storage/tests usan `tmp_path`.
- `pyproject.toml` — `pip install -e ".[dev]"`. Server: `python -m laidea.server` o `laidea-server`.

Presencia por archivo + línea (no caracter). Estar conectado ≠ estar presente. Persistir nunca propaga excepción. Identidad estable mínima por token (no auth): reconectar = mismo client_id; el ownership sobrevive reload y por eso NO se libera al desconectar (dueño que se va retiene hasta reiniciar; lo arregla la futura capa de auth). Capa 5: el lock es por presencia — si no anunciaste presencia en una línea, no la reservas; el rechazo es del update entero (sin CRDT no hay merge robusto; en práctica el update es por pulsación). Cliente NO cambió en capa 5 (server-driven; el rebote se ve como revert silencioso — pulir el aviso es follow-up).

Capas pendientes (en orden): **análisis semántico de impacto — primer lenguaje: Python** (decisión del usuario; usar `ast` de la stdlib, sin toolchain extra; dogfooding sobre el propio laidea), después notificaciones a owners, integración Git. CRDT real solo si un perfilador/uso lo justifica — la tesis es prevenir, no fusionar.

## Trampas operativas ya vistas

- **Servidor zombi en puerto 8765.** Al cambiar el protocolo, si un servidor de versión anterior sigue corriendo, los clientes nuevos hablan con él y aparecen archivos fantasma llamados "undefined" en la UI. Antes de debuggear lógica, verificar siempre: `ps aux | grep python | grep -v grep` y `lsof -i:8765`. El comando correcto para arrancar el server actual es `python -m laidea.server`, no `python server.py` (ese archivo ya no existe).

- **Auto-reload del servidor estático borra el ownership.** Síntoma: al crear un archivo o aprobar un cambio, "se pierden todos los dueños". Causa: el cliente se sirve con un static server que vigila la carpeta y recarga el navegador ante cambios (Live Server). Si la persistencia (capa 3) escribe dentro del árbol vigilado, persistir → recarga → cae el WebSocket. **Dos arreglos, ambos aplicados:** (1) el directorio por defecto de persistencia es `~/.laidea/workspace`, FUERA del repo (si pones `LAIDEA_DATA` dentro del repo, exclúyelo del watcher); (2) identidad estable mínima por token — el cliente guarda un token aleatorio en `localStorage` y lo manda en `ws://host:port/?token=...`; el server (Roster) mapea token→identidad y al reconectar devuelve el mismo client_id, así el ownership (indexado por client_id) sobrevive a CUALQUIER reload. Consecuencia de diseño asumida: el ownership ya **no se libera al desconectar** (un dueño que se va de verdad retiene sus archivos hasta reiniciar el server); el ciclo de vida real es la futura capa de auth. El token NO es auth: no se valida ni se firma, va en la URL.

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

- Solución de CRDT: descartado por defecto. La tesis es prevenir, no fusionar (ver capa 5). Solo si un perfilador/uso real lo justifica.
- Primer lenguaje para análisis semántico: **decidido — Python** (el README sugería TypeScript, pero se eligió Python: es el stack del proyecto, `ast` está en la stdlib sin toolchain externo, y permite dogfooding sobre el propio laidea). El README todavía dice "probable TypeScript" en su texto narrativo; esta línea es la que manda.
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
