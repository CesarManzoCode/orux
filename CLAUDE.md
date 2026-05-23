# Contexto del proyecto

Este directorio contiene el proyecto **Orux** (nombre definitivo del producto; el paquete Python se sigue llamando `orux` en minúscula como identificador técnico). El README.md tiene la visión completa. Léelo primero antes de hacer cualquier cosa.

## Qué estamos construyendo

Un editor colaborativo en tiempo real sobre Git para equipos de 2 a 50 devs. Capa de coordinación que previene colisiones, detecta impacto semántico de cambios automáticamente, y distribuye el conocimiento del proyecto para que el líder no sea el cuello de botella.

No reemplaza Git, GitHub, ni IDEs. No es Replit. No es governance corporativo.

## Tesis

> Misma seguridad que el flujo actual (branches, PRs, reviews, merges), sin la ceremonia. El sistema sabe sin que nadie le pregunte.

Lo que vendemos al dev: "Toca lo que necesites. El sistema se encarga de que nada se rompa."

Lo que NO vendemos: ownership, enforcement, permisos, control, vigilancia. El ownership es implementación interna (el diferencial del coche), no es lo que se vende.

## Estado actual

> **Este documento envejece rápido** — el proyecto avanza muy rápido. Ante cualquier duda, **el código y `git log` son la autoridad**, no este archivo. Última actualización: 2026-05-22.

Orux está **desplegado y en uso** en `orux.space`. Construido por capas (**33** hasta hoy). **429 tests** en el backend.

**Es un producto multi-equipo.** Cada equipo está completamente aislado:

- `TeamRuntime` vive en `backend/orux/server/runtime.py` (re-exportado por `sync.py` tras la modularización del 2026-05-21): encapsula todo el estado vivo de un equipo — su workspace (un repositorio git real), presencia, ownership, propuestas, sesiones LSP y locks. Una instancia por equipo, perezosa. Nada cruza entre equipos.
- Flujo de conexión WebSocket: autenticar (registro / login / sesión / **OAuth GitHub**) → **lobby** (crear equipo, unirse por código de invitación de un solo uso, o seleccionar uno propio) → sesión de equipo. Roles: `admin` y `member`. Cuando un `admin` entra por primera vez a un equipo virgen, se dispara el **tutorial guiado "OruxBot"** (capa 32).
- **Persistencia, dos modos.** Con `ORUX_DB_DSN` seteado (producción; `docker-compose.yml` lo hace): **Postgres** para los metadatos + un repositorio git por equipo en `/data/ws/<team_id>/`. Sin `ORUX_DB_DSN`: un equipo implícito y efímero en memoria/JSON — sólo desarrollo y tests. (El "workspace único" que describen versiones viejas de este doc es ese modo de desarrollo, no producción.)

**Backend** — `backend/orux/`, paquete `orux`, Python ≥3.11. Comandos desde `backend/`: `pip install -e ".[dev]"`, `python -m orux.server`, `pytest`.

- `protocol/` — los mensajes que viajan por WebSocket (33 tipos). Modularizado el 2026-05-21 en `messages.py` (formas), `validation.py` y `codec.py`; `__init__.py` re-exporta para que los imports externos no cambien.
- `state/` — `Document`, `Workspace`, `Roster` (presencia), `Ownership`, `Proposals`, `DiskStorage`. Todo vive por equipo, dentro del `TeamRuntime`.
- `server/` — `SyncServer` (WebSocket, puerto 8765), `TeamRuntime`, el lobby y el handshake por equipo. Modularizado el 2026-05-21: `config.py` (topes de runtime), `runtime.py` (`TeamRuntime`), `sync.py` (servidor + handshake + lobby, sigue re-exportando `TeamRuntime`).
- `teams/` + `db/` — el dominio de equipos y la persistencia Postgres (`asyncpg`, `db/schema.sql` idempotente, adaptadores `Pg*Store`; con un equivalente en memoria para los tests).
- `analysis/` — el análisis de impacto semántico. Lenguajes: Python, JS/TS, Go, Rust. Cuatro tiers; por archivo corre el más profundo disponible: Tier 0 LSP (pyright / typescript-language-server / gopls / rust-analyzer — sólo para el *fan-out*: quién usa de verdad un símbolo), Tier 1 `ast` (Python), Tier 2 tree-sitter (JS/TS/Go/Rust), Tier 3 regex. Tiene impacto transitivo (propaga por interfaz contaminada — premium), severidad alta/media/baja, y detección de rename coordinado (premium). El análisis se dispara en `Ctrl+S` (checkpoint), no por tecla.
- `identity/` — autenticación: contraseñas con PBKDF2, tokens de sesión firmados con HMAC. OAuth con GitHub end-to-end (backend + botón en `Login.tsx`).
- `git/` — `GitRepo` envuelve el binario `git`: estado, commit, clone, push, y push a la rama del equipo con link de PR. Las credenciales del usuario son efímeras, jamás se guardan.
- `api/` — **un proceso aparte** (Starlette/uvicorn, puerto 8800): la consola del operador de plataforma en `/api/v1`, los callbacks de OAuth GitHub y los webhooks de Stripe. No comparte el loop ni el estado del servidor WebSocket; un fallo acá no tumba la colaboración.
- `billing.py` — la integración con Stripe (lógica pura, sin SDK, sólo stdlib).

**Frontend** — `frontend/`, tres apps separadas:

- `frontend/ide/` — el cliente del IDE: React + TypeScript + Vite, **24 componentes**. `src/store.ts` lleva el WebSocket y el estado; i18n ES/EN modularizado el 2026-05-21 (`i18n.es.ts`, `i18n.en.ts`, lógica en `i18n.tsx`); CSS modularizado en 9 capas indexadas por `index.css` con @import. El gating es Login (con botón "Entrar con GitHub") → Hub (lobby de equipos) → IDE. El tutorial guiado **OruxBot** (capa 32) vive en `src/tutorial/` (`OruxBot.tsx`, `Tutorial.tsx`, `script.ts`, `Spotlight.tsx`, `mock.ts`) y se dispara en la primera entrada de un admin a un equipo virgen.
- `frontend/landing/` — la landing de marketing: React + framer-motion. CSS modularizado el 2026-05-21 en 3 capas. **Hero cinematográfico** (commit `113964e`): loop infinito de ~12s que narra el flujo de Orux (Ana edita → Orux detecta 4 deps → propuesta → aprobación → sincronizado) en `src/App.tsx`.
- `frontend/ops/` — `admin.html`, el panel del operador (vanilla, sin build).

**Deploy** — la raíz del repo tiene la orquestación (`docker-compose.yml`, `Dockerfile`, `Dockerfile.web`, `Caddyfile`, `Makefile`, `.env.example`). Cuatro contenedores; sólo Caddy se expone a internet: `orux` (servidor WebSocket), `api` (operador/OAuth/billing), `postgres` y `caddy` (TLS automático + proxy + estático). `Dockerfile` construye la imagen del backend (instala git, Node, pyright, typescript-language-server, rust-analyzer, el SDK de Go y gopls). `Dockerfile.web` es multi-stage: compila el frontend y lo sirve con Caddy.

**Modelo freemium** (`plans.py`): plan `free` permanente y de verdad usable (5 devs, 2 lenguajes LSP, impacto directo) frente a `premium` (sin tope, impacto transitivo, rename automático). El cobro con Stripe es **por asiento** (capa 31): un asiento por miembro del equipo, factura `precio × miembros`, la cantidad se ajusta sola cuando entra gente. Está cerrado por defecto: sin credenciales, `/api/v1/billing/*` responde 503.

**Pendientes conocidos:**
- **El tier del análisis no se expone en la UI.** El backend ya elige el tier más profundo disponible (LSP → ast → tree-sitter → regex) por archivo, pero el `ImpactMessage` no lleva ese dato y el Inspector no lo renderiza. Cuando LSP cae y degradamos a regex, el usuario no se entera — degradación silenciosa hacia el cliente, no solo a los logs.
- **Stripe en VPS:** el backend está listo pero falta config + validación en el VPS.

## Trampas operativas ya vistas

- **Servidor zombi en puerto 8765.** Al cambiar el protocolo, si un servidor de versión anterior sigue corriendo, los clientes nuevos hablan con él y aparecen archivos fantasma llamados "undefined" en la UI. Antes de debuggear lógica, verificar siempre: `ps aux | grep python | grep -v grep` y `lsof -i:8765`. El comando correcto para arrancar el server actual es `python -m orux.server`, no `python server.py` (ese archivo ya no existe).

- **Healthcheck con connect TCP crudo spamea tracebacks.** Síntoma: en los logs del contenedor, cada ~30s un `websockets.exceptions.InvalidMessage: did not receive a valid HTTP request` / `EOFError: stream ends after 0 bytes`. NO es un bug del producto: era el `HEALTHCHECK` haciendo `socket.create_connection` y cerrando sin handshake; el server websockets intentaba parsear HTTP y gritaba. Funcionalmente sano (el TCP connect igual pasa el healthcheck), solo ruido. Arreglado: el healthcheck ahora abre un WebSocket real y lo cierra (el server lo absorbe en silencio). Lección: para healthcheckear un server WS, hacé un handshake WS, no un connect pelado.

- **Dev/deploy del cliente (capa 14, React).** Dev: `cd frontend/ide && npm install && npm run dev` (Vite en :5173; `store.ts` apunta el WS a `ws://localhost:8765`, server suelto con `python -m orux.server`). Deploy: `make up` — `Dockerfile.web` es multi-stage (Node compila `frontend/ide/` → Caddy sirve `dist/`); el primer build necesita internet (corre en el VPS, no en este sandbox). Ya NO hay bind-mount de `web/` ni Live Server; el server estático que vigilaba la carpeta dejó de existir, así que la trampa de abajo es **histórica** (se conserva por la lección de fondo).
- **pyright (capa 17, Tier 0) en `python:3.12-slim`: 3 trampas, todas en el VPS.** (1) El paquete pip `pyright` (pyright-python) baja un Node prearmado que enlaza `libatomic.so.1`, y la imagen slim NO la trae → `node: error while loading shared libraries: libatomic.so.1` → pyright no levanta → el análisis degrada **mudo** a capa 16. Fix: `apt install libatomic1`. (2) pyright-python **escribe** en su cache (`PYRIGHT_PYTHON_CACHE_DIR`) en cada arranque (lock/chequeos); si el dir es read-only para el usuario runtime no-root, el langserver no inicia. Fix: `chown` ese dir al usuario runtime, no `chmod a+rX`. (3) Diseño: el `documentSymbol` de pyright **no rellena la firma en `detail`** → no sirve para DETECTAR qué cambió. Regla: la detección de cambio de interfaz la hace la jerarquía de capa 16 (`ast` ya aísla firma/superficie); pyright aporta **solo el fan-out** (`references`, resolución real de quién usa el símbolo). Lección transversal: un componente que **degrada en silencio** es invisible en producción — `arrancar_pyright` loguea la razón exacta + cola de stderr; sin esa instrumentación las 3 trampas habrían sido a ciegas.

- **(Histórico, pre-React) Auto-reload del servidor estático borra el ownership.** Síntoma: al crear un archivo o aprobar un cambio, "se pierden todos los dueños". Causa: el cliente se servía con un static server que vigilaba la carpeta y recargaba el navegador ante cambios (Live Server). Si la persistencia (capa 3) escribe dentro del árbol vigilado, persistir → recarga → cae el WebSocket. **Dos arreglos:** (1) el estado de ejecución vive bajo `~/.orux/` (workspace en `~/.orux/workspace`, + `users.json`/`ownership.json`/`secret`), FUERA del repo; `ORUX_DATA` ahora apunta al **directorio base** (antes al de workspace); si lo pones dentro del repo, exclúyelo del watcher. (2) Capa 7 reemplazó el token anónimo por **identidad real**: login obligatorio, identidad = usuario (determinista), ownership por usuario persistido que sobrevive a CUALQUIER reload y a reiniciar el server. El ownership ya **no se libera al desconectar** (un dueño que se va retiene hasta que otro mecanismo lo gestione — trabajo posterior, no prototipo).

## Principios para colaborar en este proyecto

- **Idioma: español.** Toda comunicación, comentarios, mensajes de commit y artefactos en español.
- **Construcción por capas.** Orden estricto: estado compartido → edición en tiempo real → ownership → análisis semántico → notificaciones → integración Git. No se añade una capa hasta que la anterior funcione.
- **Cada capa: "real pero mínima".** Estructura y tests desde el primer commit. Nada de abstracciones para problemas que aún no existen. Si una capa empieza a requerir "ah pero también necesito X y Y", son dos capas, se separan.
- **Riesgo crítico identificado: feature soup.** Resistir proponer features extra. Una capa increíble vale más que veinte mediocres.
- **El núcleo es la coordinación semántica, no el editor.** El editor es vehículo.
- **Stack: Python.** Es el lenguaje principal del usuario. Para el realtime hot path se migrará selectivamente solo si un perfilador lo justifica.

## Decisiones ya tomadas

- Plataforma fase 1: web app.
- Plataforma fase 2: ir al entorno del dev (plugins de VSCode, JetBrains) — diferido, no empezado.
- Sobre Git: integración, no reemplazo. `git clone` debe bastar.
- Sin modo offline. El estado compartido en tiempo real es la base.
- Público objetivo inicial: equipos nuevos sin inercia, open source que empieza, founders técnicos de 2-3 personas.
- Decisor de adopción: el líder del equipo (CTO, tech lead, founder técnico).
- **Hay base de datos: Postgres.** La decisión vieja de "sin DB" se revirtió al llegar el multi-equipo (capa 15): los metadatos (usuarios, equipos, miembros, invitaciones, ownership) viven en Postgres; el contenido de los archivos sigue siendo un repositorio git por equipo en disco, así que "un `git clone` basta" se mantiene.
- **Nombre del producto: Orux** (decidido).
- **Análisis semántico: empezó en Python y hoy cubre Python, JS/TS, Go y Rust.** Python primero fue deliberado: es el stack del proyecto, `ast` está en la stdlib sin toolchain externo, y permite dogfooding sobre el propio Orux.
- **Modelo de negocio: freemium.** Plan free permanente y usable (los límites son de escala, nunca de la tesis); premium por escala y profundidad de análisis. Cobro con Stripe, suscripción mensual **por asiento** (capa 31): un asiento por miembro del equipo, como el plan Business de ChatGPT. La factura es `precio_por_asiento × miembros`; la cantidad de la suscripción se ajusta sola cuando entra gente nueva a un equipo premium. El precio actual es de prueba.
- **Regla de dependencias:** el "cero deps" fue disciplina de prototipo, no permanente. Una dependencia entra cuando hay un cuello de botella concreto que esa dep resuelve — por evidencia, no preventivo. Hoy el backend tiene ~9 dependencias (websockets, asyncpg, tree-sitter, pyright, starlette/uvicorn, …), cada una entró por una necesidad real.
- CRDT: descartado por defecto. La tesis es prevenir la colisión con coordinación, no fusionarla después. Sólo si un perfilador o el uso real lo justifican.

## Diferido (no hacer sin que el usuario lo pida)

- **Análisis grado-compilador:** resolución de tipos cross-módulo de verdad. El usuario lo enmarca como un muro económico (costo de cómputo), no técnico — no se construye hasta que haya usuarios pagando.
- **Branches / PR management completo y pull/merge de conflictos.** Hoy Orux hace push a la rama del equipo y da el link para abrir el PR en GitHub; la resolución de conflictos se esquiva por tesis (prevenir, no fusionar).
- Escalado horizontal.
- La fase 2 (plugins de IDE).

## Cómo se debe sentir el producto

- "Misma vida, menos dolor."
- Live collaborative review, no governance corporativo.
- Multiplayer semantic coding.
- El dev no se siente bloqueado antes de intentar.
- El owner no siente que invadieron su código.
- Editar primero. Negociar después. Aplicar al final.
