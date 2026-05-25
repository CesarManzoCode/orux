# Domain: protocol

`backend/orux/domain/protocol/` define los mensajes del WebSocket: shapes (dataclasses), codec JSON, validación.

## Estructura

```
protocol/
├── messages.py     33 dataclasses (un Message por tipo)
├── codec.py        encode / decode (JSON) + topes de tamaño
└── validation.py   helpers de validación tipada
```

`protocol/__init__.py` re-exporta los tipos más usados (Messages + `encode`/`decode`) para un solo import: `from orux.domain.protocol import UpdateMessage, encode, ...`.

## Mensajes (33 tipos)

Cada mensaje es un `@dataclass` con un campo `type: Literal[...]` y los campos del payload.

### Authentication (4)

| Mensaje | Direction | Payload |
|---|---|---|
| `RegisterMessage` | C→S | `username, password` |
| `LoginMessage` | C→S | `username, password` |
| `SessionMessage` | C→S | `token` |
| `AuthOkMessage` | S→C | `client_id, name, token` |
| `AuthErrorMessage` | S→C | `code, mensaje` |

### Lobby (5)

| Mensaje | Direction | Payload |
|---|---|---|
| `LobbyMessage` | S→C | `equipos: list[{id, nombre, rol, plan, miembros}]` |
| `CreateTeamMessage` | C→S | `nombre` |
| `RedeemInviteMessage` | C→S | `code` |
| `SelectTeamMessage` | C→S | `team_id` |
| `TeamReadyMessage` | S→C | `team_id, nombre, rol` |

### Sesión de equipo (10+ handshake + bucle)

| Mensaje | Direction | Payload |
|---|---|---|
| `InitMessage` | S→C | `documents: dict[path, content]` (snapshot del workspace al boot) |
| `WelcomeMessage` | S→C | `client_id, name, color, others: list[PresenceState]` |
| `OwnershipMessage` | S→C | `owners: dict[path, username]` (snapshot completo, broadcast en cada cambio) |
| `AdminInfoMessage` | S→C | `is_admin, members: list[{usuario, rol}]` |
| `GitStatusMessage` | S→C | `disponible, rama, cambios, commits: list[str]` |
| `LeaveMessage` | C→S | (no payload) |

### Edición (5)

| Mensaje | Direction | Payload |
|---|---|---|
| `UpdateMessage` | C↔S | `path, content` |
| `SaveMessage` | C→S | `path` (Ctrl+S, dispara análisis) |
| `DeleteMessage` | C↔S | `path` |
| `ClaimMessage` | C→S | `path` |
| `PresenceMessage` | C↔S | `client_id, name, color, path, line` |

### Ownership admin (4)

| Mensaje | Direction | Payload |
|---|---|---|
| `AdminAssignMessage` | C→S | `path, username` (vacío = revocar) |
| `AdminAssignManyMessage` | C→S | `paths: list[str], username` |
| `CreateInviteMessage` | C→S | (no payload) |
| `InviteCreatedMessage` | S→C | `code` |

### Tentativas (2)

| Mensaje | Direction | Payload |
|---|---|---|
| `ProposalMessage` | S→C | `proposal: Proposal{id, path, author_id, author_name, content}` |
| `ResolveMessage` | C→S | `proposal_id, accept` |

### Impacto (1)

| Mensaje | Direction | Payload |
|---|---|---|
| `ImpactMessage` | S→C | `source_path, author_name, affected_path, symbols, motivos, severidades, cadena?, analizador?` |

### Git (5)

| Mensaje | Direction | Payload |
|---|---|---|
| `GitRefreshMessage` | C→S | (no payload — pide refresh del estado) |
| `CommitMessage` | C→S | `message` |
| `CloneMessage` | C→S | `url, username, token` (destructivo) |
| `PushMessage` | C→S | `url?, username, token, rama?` |
| `GitResultMessage` | S→C | `ok, detalle, pr_url?` |

## Codec (`codec.py`)

```python
def encode(msg: Message) -> str:
    # dataclasses.asdict + json.dumps. Salida string para `websocket.send`.

def decode(raw: bytes | str) -> Message:
    # Lee `type`, busca la clase, valida payload, construye dataclass.
    # Rechaza si:
    #   - frame > MAX_FRAME_BYTES (1 MB) → ProtocolError
    #   - JSON inválido → ProtocolError
    #   - `type` desconocido → ProtocolError
    #   - campos faltantes/tipos incorrectos → ProtocolError
```

`MAX_FRAME_BYTES = 1024 * 1024` (1 MB). Alineado con `MAX_BYTES_ARCHIVO` del workspace y `MAX_CONTENT_BYTES` de propuestas.

## Validación (`validation.py`)

Helpers tipados que `codec.decode` usa para validar cada campo:

- `_str(valor, *, permitir_vacio=False)`: requiere `str` no None y opcionalmente no-vacío.
- `_int(valor, *, minimo, maximo)`: requiere `int` (no `bool`!) en rango.
- `_bool(valor)`: requiere `bool` estricto.
- `_dict_str_str(valor)`: requiere `dict[str, str]`.
- `_list_str(valor, *, max_len)`: requiere lista de strings con tope.
- `_lobby_team(d)`: shape `{id, nombre, rol, plan, miembros}` con tipos.
- `ProtocolError`: la excepción que todos levantan cuando algo no cuadra.

### Fix BACKEND-AUDIT (Sprint G.1)

Bug semántico crítico arreglado el 2026-05-23: `_str(permitir_vacio=False)` antes solo rechazaba `None`, ahora rechaza también `""`. Por carambola, endureció todos los campos obligatorios del protocolo (path, username, password, token, code, team_id, …) que ahora rechazan string vacío.

## Por qué el codec vive en `domain/`

Es una decisión consciente. El protocolo ES parte del dominio público de Orux — define qué puede pasar entre cliente y servidor. No es "infraestructura"; es contrato del producto.

Los tipos de mensaje no dependen de WebSocket: son shapes JSON. Mañana el transporte podría ser SSE, HTTP long-polling o gRPC y los mensajes serían los mismos (con otro envelope). Por eso vive en `domain/`, no en `adapters/inbound/websocket/`.

## Frontend reusa estos tipos

`frontend/ide/src/store.ts` tiene un `Message` discriminated union (TypeScript) que es **manualmente** equivalente a `messages.py`. No hay code-gen — son archivos hermanos que deben mantenerse en sync cuando se agrega un mensaje. La testería del backend valida los shapes; el cliente confía.

Si el sistema crece, generar tipos TS desde Python sería una mejora obvia (`pydantic` → `pydantic-to-typescript`, o un script custom).
