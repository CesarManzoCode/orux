# Dominio

El dominio vive en `backend/orux/domain/`. Es **puro**: no importa Postgres, ni WebSockets, ni Stripe. Sus únicas dependencias son la stdlib + utilities cross-cutting (`orux/_env.py`, `orux/_net.py`).

## Qué hay en `domain/`

```
domain/
├── state/        Workspace, Ownership, Proposals, Roster, locks, paths, storage (DiskStorage), document
├── identity/     UserStore + passwords + tokens + oauth (todo puro)
├── plans.py      Free vs premium, límites
├── protocol/     Mensajes WS, codec, validación
├── billing.py    Funciones puras de Stripe (HMAC verify, parsers, builders)
├── analysis/     Tiers, impacto, motivos, rename, transitive, lsp, modelo, treesitter, python/javascript/go/rust
└── teams/        MemTeamStore + validar_nombre_equipo
```

Cada paquete tiene su documentación detallada en [`docs/domain/`](../domain/). Acá explico la lógica de conjunto.

## El concepto central: ownership

El producto previene colisiones con **coordinación, no merge**. Cada archivo puede tener un dueño:

- **Sin dueño**: cualquiera lo edita y se aplica directo. Quien lo edita primero se vuelve dueño automáticamente.
- **Con dueño**: solo el dueño aplica cambios directo. Otros mandan **propuestas tentativas**; el dueño aprueba o rechaza.

`state.Ownership` es el mapa `path → username`. Es memoria pura sync con `threading.Lock` interno. La persistencia es externa (vía `OwnershipStorePort`).

## El workspace

`state.Workspace` es un `dict[path, Document]` (el `Document` es solo un wrapper `{content: str}`). Es la fuente de verdad del servidor sobre qué archivos existen y qué contienen.

Topes (configurables vía env, defaults seguros):

| Tope | Default | Por qué |
|---|---|---|
| `MAX_ARCHIVOS` | 50.000 | Un monorepo grande va por debajo. |
| `MAX_BYTES_ARCHIVO` | 1 MB | Alineado con `protocol.MAX_FRAME_BYTES`. |
| `MAX_BYTES_TOTAL` | 256 MB | Cabe cómodo en memoria por equipo. |

Cuando un update rebasaría los topes, `Workspace.update` levanta `WorkspaceLleno` y NO toca memoria/disco; el server lo propaga al cliente como mensaje de error.

## Las propuestas tentativas

`state.Proposals` mantiene un dict `{id: Proposal}` donde el `id` es determinista (`path::author_id`). El ID determinista hace que **mientras un dev sigue tecleando sobre un archivo con dueño ajeno, sus pulsaciones reemplazan la propuesta** en vez de acumular una propuesta por tecla. El dueño siempre ve la versión más reciente.

Reentrega: si el dueño no estaba online al crearse una propuesta, queda en `Proposals` y el server se la reentrega al final del handshake cuando vuelve.

Topes (mitigan abuso por un atacante con cuenta):

- `MAX_CONTENT_BYTES` = 1 MB (igual que un update legítimo).
- `MAX_POR_AUTOR` = 50 propuestas pendientes por autor por equipo.

## La presencia

`state.Roster` mantiene quién está en qué archivo y en qué línea. Para que cuando dos personas tocan el mismo archivo sin dueño, el segundo vea al primero y NO pueda escribir sobre las líneas que el otro está editando (capa 5: colisiones por línea).

`Roster.mover(client_id, path, line)` actualiza la posición y devuelve el estado nuevo (o `None` si no cambió nada). `Roster.lineas_ocupadas(path, excepto)` devuelve las líneas ocupadas por otros en ese archivo (para validar updates entrantes).

## La identidad

`identity.UserStore` es memoria pura sync con un `dict[username, registro]`. El `registro` puede ser un string (legacy: solo el hash de pwd) o un dict `{hash, epoch}` con el contador de sesiones del usuario.

- **Password**: PBKDF2 con sal aleatoria por hash. `passwords.hash_password()` valida tamaño (>=8, <=128).
- **Normalización**: `normalizar(username) = username.strip().lower()`. Mismo dueño aunque cambien mayúsculas/espacios.
- **Externos (OAuth)**: `asegurar_externo()` crea una cuenta con `MARCADOR_EXTERNO` (que `verificar_password` rechaza siempre): existe para `existe()` pero NO se puede entrar por contraseña.
- **Reglas de formato** (solo al crear): ASCII alfanumérico + `._-`, 2-32 chars, no empieza con puntuación, prefijo `gh:` reservado. Cuentas viejas siguen funcionando aunque no cumplan.

## Los tokens

`identity.tokens.crear_token(user, secret, ttl_seg, *, epoch, kid)` emite `<payload_b64>.<hmac_hex>`. El payload es JSON: `{user, epoch, exp?, kid?}`.

`usuario_de_token(token, secret, *, epoch_de)` valida y devuelve el usuario o None. Acepta el secret como `str` (modo histórico), `list` (rotación con fallback ordenado) o `dict {kid: secret}` (rotación atómica por kid).

Robustez crítica:

- **exp** (epoch UTC): vida acotada si se filtra el token.
- **epoch** por usuario: revocación quirúrgica (cambio de password o `revocar_sesiones()` incrementa el epoch y los tokens viejos dejan de valer).
- **kid**: rotación atómica del secret.
- **Domain separation HMAC**: la firma incluye un prefijo `orux-session\x00` para que un atacante no pueda hacer pasar un state CSRF de OAuth como un token de sesión.

## El protocolo

`protocol/messages.py` define los 33 tipos de mensaje del WS como dataclasses. `protocol/codec.py` los serializa/deserializa a JSON; `protocol/validation.py` valida tipos.

Cada mensaje es una clase con `type: Literal[...]` y los campos del payload. El codec hace `dataclasses.asdict` + json.dumps; el decoder lee el `type`, busca la clase, y construye con los campos validados.

`MAX_FRAME_BYTES` = 1 MB. Un frame más grande se rechaza con `ProtocolError`; el server lo trata como mensaje malo.

## El análisis semántico

`analysis/` es **el** diferencial del producto: detectar cambios que importan a otros archivos. Tiene una jerarquía de tiers (capa 16):

| Tier | Lenguaje | Cómo |
|---|---|---|
| 0 (LSP) | Python, JS/TS, Go, Rust | pyright / typescript-language-server / gopls / rust-analyzer. Solo para el *fan-out* (resolución real de "quién usa este símbolo"). |
| 1 (AST) | Python | `ast` de la stdlib. Extracción de símbolos + firma + superficie. |
| 2 (tree-sitter) | JS/TS, Go, Rust | tree-sitter (parser C universal). |
| 3 (regex) | fallback | Token-scan. |

Por archivo corre el tier más profundo disponible. El motor `impacto(workspace, path, viejo, nuevo, sesion)` devuelve `{símbolo_cambiado: [archivos_afectados]}`.

Premium agrega:

- **Impacto transitivo** (`transitive.py`): propaga por interfaz contaminada — no por "referencias de referencias" (eso explota en ruido). Si cambiar S llega a R, y R expone S en su interfaz (firma/constructor/superficie), R también se propaga.
- **Rename detection + codemod**: `rename.detectar_rename(viejo_simbolos, nuevo_simbolos)` detecta renames de miembro confiables; `aplicar_rename(contenido, viejo, nuevo)` hace el reemplazo en archivos que usan la clase.

## Los planes

`plans.py` es el esqueleto del freemium (capa 22). Decisión decretada con el usuario: **tiers por escala, no medidor que se agota**. El free es permanente y orux funciona de verdad ahí; las limitaciones son de escala/recurso (max 5 devs, max 2 lenguajes LSP, impacto directo), nunca de capacidad.

| Plan | max_devs | max_langs | impacto | rename | workspaces |
|---|---|---|---|---|---|
| free | 5 | 2 | directo | manual | 1 |
| premium | INF | INF | transitivo | automático | INF |

Funciones puras: `limites(plan)`, `permite_miembro(plan, miembros_actuales)`, `permite_lenguaje(plan, langs_activos)`, `permite_rename(plan)`, etc.

## Billing puro

`billing.py` tiene las funciones puras de Stripe (sin red):

- `params_checkout(...)`: arma el body form-urlencoded para crear una sesión de Checkout (cobro por asiento).
- `verificar_firma_webhook(payload, header, secret)`: HMAC-SHA256 sobre `"{t}.{payload}"` con tolerancia de 300s anti-replay.
- `evento_de_payload(payload)`: parsea el JSON del webhook.
- `cambio_de_plan(evento)`: traduce `checkout.session.completed → premium` y `customer.subscription.deleted → free`.
- `suscripcion_de_evento(evento)`: extrae el `sub_...` para el ajuste de asientos.
- `event_id_de(evento)`: extrae el `evt_...` para idempotencia.

La llamada de red real (POST a Stripe) vive en `orux/stripe_client.py` (no en `domain/`).

## Teams (puro)

`teams.store` tiene `MemTeamStore` (implementación en memoria que cumple `TeamStorePort`) y los validators puros:

- `validar_nombre_equipo(nombre)`: trim, colapsa espacios, rechaza control chars / invisibles Unicode / HTML / >40 chars.
- `INVITE_TTL_DAYS = 7`: TTL canónico (la SQL del Pg adapter usa el mismo número).

`MemTeamStore` vive aquí (no en `adapters/outbound/`) porque es trivial y "in-memory" no es realmente una infraestructura — es la implementación de referencia que define la semántica que `PgTeamStore` debe replicar.

## Cosas que NO están en el dominio

- WebSocket / Starlette / Stripe HTTP client.
- `asyncpg` (vive en `adapters/outbound/postgres/`).
- `subprocess` (vive en `adapters/outbound/git/` y `analysis/lsp.py`).
- La persistencia inline JSON de `Ownership` y `UserStore` (movida a adapters JSON tras el refactor hex).
