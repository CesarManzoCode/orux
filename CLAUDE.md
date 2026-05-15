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

Fase muy temprana. La idea completa vive en `README.md`. Existen ya las **capas 1 y 2** implementadas como paquete Python instalable:

- `laidea/protocol/` — capa 1: `InitMessage(files)`, `UpdateMessage(path, content)`. Capa 2: `WelcomeMessage(you, peers)`, `PresenceMessage(client_id, name, color, path, line)`, `LeaveMessage(client_id)`, más el tipo de estado `PresenceState`. Encode/decode con `asdict`.
- `laidea/state/` — `Document` (un archivo, todavía un string), `Workspace` (mapa path → Document), `Roster` (presencia: client_id → PresenceState; el server asigna identidad anónima, el cliente no la elige).
- `laidea/server/` — `SyncServer` aplica updates al workspace y retransmite (no eco al emisor). Al conectar manda `init` y luego `welcome`. Retransmite presencia fusionando la identidad confiable; avisa con `leave` al desconectar (solo si el cliente llegó a estar presente en algún archivo).
- `web/index.html` — cliente con sidebar (badges de color por archivo), cabecera "quién está aquí", y marcas de línea de cada peer sobre el textarea. El textarea usa `white-space: pre` y `line-height` en px fijos (22) para alinear línea↔pixel; `LINE_H`/`PAD_TOP` en el JS deben coincidir con el CSS.
- `tests/` — 26 tests con `pytest` y `pytest-asyncio`. Contratos clave intactos: `init` sigue siendo el primer mensaje, broadcasts de update SIEMPRE incluyen `path`. El helper `handshake()` en `test_sync.py` consume `init`+`welcome`.
- `pyproject.toml` — `pip install -e ".[dev]"`. Server: `python -m laidea.server` o `laidea-server`.

Presencia es por archivo + número de línea (decisión deliberada, no posición de caracter). Estar conectado ≠ estar presente: un cliente sin archivo abierto no se difunde ni aparece en ningún roster.

Capas pendientes (en orden): **persistencia es la siguiente**, después CRDT real, ownership, análisis semántico, notificaciones a owners, integración Git.

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
