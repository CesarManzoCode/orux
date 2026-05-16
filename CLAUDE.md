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

Prototipo completo y **desplegado en `studymation.online`**, probándose con devs reales. Las **8 capas del README + capas 9-12** están implementadas como paquete Python instalable. La idea completa vive en `README.md`; el estado capa-por-capa al día vive en la memoria del proyecto (`laidea_project.md`). Resumen de lo añadido sobre las capas 1-5 descritas abajo:

- `laidea/protocol/` — capa 1: `Init`, `Update`. Capa 2: `Welcome`, `Presence`, `Leave` + estado `PresenceState`. Capa 4: `ClaimMessage(path)`, `OwnershipMessage(owners)`, `ProposalMessage(proposal)` + estado `Proposal`, `ResolveMessage(proposal_id, accept)`. Encode/decode con `asdict`.
- `laidea/state/` — `Document`, `Workspace` (storage opcional; `exists()` distingue crear de editar), `Roster` (presencia efímera + identidad estable por token: `asignar(token)`, `lineas_ocupadas()`), `DiskStorage` (capa 3), `Ownership` (capa 4: efímero, NO se libera al desconectar — sobrevive por token), `Proposals` (capa 4: id `path::author_id`), `lineas_tocadas` (capa 5: diff LCS, líneas del viejo que el nuevo borra/modifica; insertar NO toca las desplazadas).
- `laidea/server/` — `SyncServer(storage=None)`. Handshake de 3 mensajes: `init`→`welcome`→`ownership`. Crear archivo (primer update sobre path nuevo sin dueño) hace dueño al creador. Update de no-dueño sobre archivo con dueño = propuesta. Capa 5: si el archivo NO tiene dueño y el update pisa una línea ocupada por otro presente, se rechaza (se devuelve lo autoritativo al emisor, `continue`); el dueño no tiene lock. `resolve` aprobar = `_broadcast_todos`; rechazar = revierte al autor. Al desconectar: libera ownership, descarta sus propuestas. `__main__` cablea `DiskStorage`.
- `web/index.html` — sidebar con badges de presencia; marcas de línea sobre el textarea (`white-space: pre`, `line-height` 22px fijo; `LINE_H`/`PAD_TOP` en JS deben coincidir con CSS). Capa 4: chip de dueño + botón "reclamar", aviso al autor de cambio tentativo, bandeja del dueño con diff por líneas (LCS) y botones aprobar/rechazar.
- `laidea/analysis/` — capa 6 + 11: pluggable por lenguaje. `python.py` (vía `ast`) y `javascript.py` (js/jsx/ts/tsx, `re`, heurístico por nombres — top-level incl. type/interface/enum, refs sin ruido de strings). `__init__.impacto` despacha por extensión y NO cruza lenguajes; `.py` da resultado idéntico al de antes (tests capa 6 sin cambios). NO es compilador (ni el de Python lo era): la versión con tipos cross-módulo sigue diferida para AMBOS.
- `laidea/identity/` — capa 7: `passwords.py` (PBKDF2 stdlib), `tokens.py` (token de sesión firmado HMAC), `store.py` (`UserStore`: usuarios JSON, DI por ruta, `path=None`=memoria, usuario normalizado trim+minúsculas). Cero deps nuevas.
- `laidea/git/` — capa 8: `GitRepo` envuelve el binario `git` (subprocess, no reimplementa). `asegurar()`=git init idempotente; `estado()`→`EstadoGit(disponible, rama, cambios, commits)`. git ausente/fallo → `disponible=False`, nunca explota. `root=None`=deshabilitado. Solo lectura.
- `tests/` — 112 tests. Capa 7: `autenticar(ws, user=, registrar=)` pasa la compuerta; `handshake()` = autenticar + init+welcome+ownership (los tests que leen `init` a mano hacen `await autenticar(c)` antes). Capa 8: git=None por defecto → no `git_status`, handshake intacto; el test git usa `GitRepo(tmp)` con repo real. Contratos intactos: update broadcasts con `path`, nunca eco al emisor. `test_*.py` puros: locks/presence/analysis/identity/git. `tmp_path` para storage/git; users/ownership memoria (None).
- **Capas 9-12** (sobre lo anterior): **9** eliminar archivos + commit desde la web (autor = usuario autenticado, sin push). **10** clone destructivo + push con credenciales usuario+token **EFÍMERAS jamás guardadas** (`GitRepo._git_cred`: token solo en env del subproc, `GIT_ASKPASS` temporal sin el token, salida scrubeada, nunca en argv/URL/.git/logs; clone seguro-primero; `_git_lock` serializa git). **11** 1ª dependencia real: **Prism.js** vendorizado en `web/vendor/prism.js` (resaltado multilenguaje; el usuario lo baja en el VPS — sandbox sin internet; degrada a vanilla/plano con try/catch, NUNCA aborta el editor; NO se usa su theme → métrica de presencia intacta) + análisis de impacto multilenguaje. **12** admin del workspace: `UserStore.admin()` (= primer registrado, sin migrar JSON) + `Ownership.asignar()` (override que `claim` no hacía); `AdminInfoMessage` cierra el handshake fijo (init/welcome/ownership/admin_info, con o sin git); `AdminAssignMessage` solo-admin reparte/revoca ownership; panel `#adminp` en el cliente (solo lo ve el admin). Era el bloqueo para soltárselo a un equipo open source ya hecho.
- `tests/` — **153 tests** (`test_admin.py` puro + flujo admin en `test_sync.py`). `handshake()` consume init+welcome+ownership+admin_info.
- `pyproject.toml` — `pip install -e ".[dev]"`. Server: `python -m laidea.server` o `laidea-server`.

Presencia por archivo + línea (no caracter). Estar conectado ≠ estar presente. Persistir nunca propaga excepción. Identidad = usuario real autenticado (capa 7): la app está cerrada (sin login no hay init); reconectar/loguearse = misma identidad determinista (color = hash del usuario); ownership por usuario, persistido, NO se libera al desconectar. Capa 5: el lock es por presencia — si no anunciaste presencia en una línea, no la reservas; el rechazo es del update entero (sin CRDT; en práctica el update es por pulsación). El rebote del lock se ve como revert silencioso (pulir el aviso es follow-up).

Capa 6 (análisis de impacto, Python) COMPLETA y validada end-to-end por el usuario (2 users). Capa 7 (IDENTIDAD REAL) COMPLETA. Capa 8 (Git, solo lectura) COMPLETA: 1/3 núcleo `GitRepo` ✅ · 2/3 server (`git=GitRepo|None`; `git_status` tras handshake; `git_refresh` bajo demanda, NO por tecla; `git.estado()` en hilo) ✅ · 3/3 panel `#git` en el sidebar ✅. `__main__` cablea `GitRepo(~/.laidea/workspace)` = MISMO dir que DiskStorage → workspace ES repo git. `DiskStorage.cargar()` excluye `.git/`. **Capa 9** (pulido para uso real, decidido tras desplegar): 9a **eliminar archivos** (`DeleteMessage`; `Workspace.delete`/`DiskStorage.borrar`/`Ownership.liberar`/`Proposals.drop_path`; solo borra el dueño o cualquiera si no tiene dueño; `_broadcast_todos`; cliente: ✕ por archivo). 9b **commit desde la web** (`CommitMessage`→`GitRepo.commitear` con autor = usuario autenticado vía `_autor_git`, sin push; `GitResultMessage` de feedback; tras commit ok se difunde `git_status` a todos; cliente: caja de commit en el panel git, reemplazó el hint de terminal que en deploy no aplicaba). **Las 8 capas del README implementadas + capa 9 de pulido.** Server: `_autenticar` (register/login/session) ANTES de init/welcome/ownership; identidad = usuario real (Roster.asignar(usuario), color = hash); ownership por usuario y persistido (`Ownership(path)`), ya no se libera al desconectar; token de sesión firmado HMAC, secreto en `~/.laidea/secret`. Cliente: overlay `#login` (entrar/crear cuenta), auto-login con `laidea_session` de localStorage, botón "salir". `SyncServer(storage, users, ownership, secret)` — inyectado, None=memoria en tests. Empaquetado para deploy (sin features nuevas): `Dockerfile` (server, no-root, git instalado, /data volumen), `docker-compose.yml` (laidea sin puertos + Caddy único expuesto: estático+TLS+proxy `/ws`), `Caddyfile`, `Makefile`, `.dockerignore`, `.env.example`. **SIN base de datos** (decisión del usuario): users/ownership JSON + workspace=git sobre volumen persistente; el volumen da la durabilidad, no un motor de DB (coherente con "git clone basta"). Cliente: la URL del WS se deriva del origen (dev=`ws://localhost:8765` por puerto 5500/file://; deploy=`wss://host/ws`). Server: `LAIDEA_HOST`/`LAIDEA_PORT`/`LAIDEA_DATA` por env (default `localhost` para no exponerse en dev; el contenedor pone `0.0.0.0`).

**Capa 10 (Git remoto, escalón mínimo) COMPLETA**: clone (destructivo, reemplaza el workspace único, cliente confirma) + push, credenciales usuario+token **EFÍMERAS, nunca guardadas**. Mecanismo (la parte sensible, `GitRepo._git_cred`): token solo en el env del subproceso, `GIT_ASKPASS` script temporal 0700 que NO contiene el token, `credential.helper=` vacío, `GIT_TERMINAL_PROMPT=0`, salida scrubeada (token→`***`); nunca en argv/URL/`.git/config`/logs. clone seguro-primero (clona a temporal; solo si OK reemplaza → un clone fallido NO destruye). push NO fusiona: si el remoto avanzó lo dice claro (pull/merge = diferido, no se finge). Server: `_git_lock` serializa commit/clone/push; tras clone OK, `_reiniciar_para_todos` (recarga workspace, `Ownership.reset`, propuestas nuevas, re-init init/ownership/git_status a todos los autenticados). Cliente: panel git con inputs URL/usuario/token (token nunca en localStorage ni entre re-renders; url/usuario en memoria de sesión), botones clonar/push; `init` ahora REEMPLAZA (no fusiona) para que el re-init limpie lo viejo. Solo seguro sobre wss (prod lo es).

**El gran arco pendiente (decidido diferir, NO hacer sin que el usuario lo pida)**: multi-proyecto/equipos, workspaces efímeros (clonar al abrir, "aplicar o se pierde" al cerrar). Riesgos a resolver EN DISEÑO antes de codear: perder trabajo si crashea/cierra, y push rechazado = "resolver después" (lo que la tesis evita). También diferido: branches/PRs, base de datos, escalado horizontal, multi-lenguaje, CRDT. La dificultad "absurda" no se venció — se difirió con disciplina; sigue ahí (CRDT esquivado, análisis semántico mínimo, este arco multi-proyecto).

## Trampas operativas ya vistas

- **Servidor zombi en puerto 8765.** Al cambiar el protocolo, si un servidor de versión anterior sigue corriendo, los clientes nuevos hablan con él y aparecen archivos fantasma llamados "undefined" en la UI. Antes de debuggear lógica, verificar siempre: `ps aux | grep python | grep -v grep` y `lsof -i:8765`. El comando correcto para arrancar el server actual es `python -m laidea.server`, no `python server.py` (ese archivo ya no existe).

- **Healthcheck con connect TCP crudo spamea tracebacks.** Síntoma: en los logs del contenedor, cada ~30s un `websockets.exceptions.InvalidMessage: did not receive a valid HTTP request` / `EOFError: stream ends after 0 bytes`. NO es un bug del producto: era el `HEALTHCHECK` haciendo `socket.create_connection` y cerrando sin handshake; el server websockets intentaba parsear HTTP y gritaba. Funcionalmente sano (el TCP connect igual pasa el healthcheck), solo ruido. Arreglado: el healthcheck ahora abre un WebSocket real y lo cierra (el server lo absorbe en silencio). Lección: para healthcheckear un server WS, hacé un handshake WS, no un connect pelado.

- **Auto-reload del servidor estático borra el ownership.** Síntoma: al crear un archivo o aprobar un cambio, "se pierden todos los dueños". Causa: el cliente se sirve con un static server que vigila la carpeta y recarga el navegador ante cambios (Live Server). Si la persistencia (capa 3) escribe dentro del árbol vigilado, persistir → recarga → cae el WebSocket. **Dos arreglos:** (1) el estado de ejecución vive bajo `~/.laidea/` (workspace en `~/.laidea/workspace`, + `users.json`/`ownership.json`/`secret`), FUERA del repo; `LAIDEA_DATA` ahora apunta al **directorio base** (antes al de workspace); si lo pones dentro del repo, exclúyelo del watcher. (2) Capa 7 reemplazó el token anónimo por **identidad real**: login obligatorio, identidad = usuario (determinista), ownership por usuario persistido que sobrevive a CUALQUIER reload y a reiniciar el server. El ownership ya **no se libera al desconectar** (un dueño que se va retiene hasta que otro mecanismo lo gestione — trabajo posterior, no prototipo).

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
- **Regla de dependencias** (acordada con el usuario): el "cero deps" fue disciplina de prototipo, no permanente. Una dependencia entra cuando un **usuario real** choca con un cuello de botella concreto que esa dep específica resuelve — por evidencia, no preventivo, idealmente post-validación. La primera prevista: un editor real (CodeMirror) cuando el resaltador casero vanilla toque su techo con gente usándolo. Hasta entonces, vanilla/stdlib.
- **Pulido de UX (capa de testeabilidad, sin features ni deps)**: árbol de carpetas colapsable (reemplazó la lista plana de rutas), ergonomía de editor (cerrar pares, Tab=4, Enter mantiene sangría) y resaltado de sintaxis Python como overlay `<pre>` detrás del textarea transparente (misma técnica/métricas que el overlay de presencia; no reemplaza el editor → presencia/locks/tentativo intactos). Heurístico, no compilador.

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
