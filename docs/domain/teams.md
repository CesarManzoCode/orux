# Domain: teams

`backend/orux/domain/teams/store.py` modela el dominio de equipos: creación, membresía, invitaciones. Tiene `MemTeamStore` (in-memory para tests/dev) + los validators puros.

El adapter Postgres (`PgTeamStore`) vive en `adapters/outbound/postgres/teams.py` y cumple la misma superficie async (el `TeamStorePort` los iguala formalmente).

## Reglas del dominio (decididas con el usuario)

1. **El que crea un equipo es su `admin`.** El admin invita; los demás se unen redimiendo un código de un solo uso.
2. **Cualquiera puede tener cuenta**, pero sin pertenecer a un equipo NO ve nada (lo hace cumplir el server; el store solo dice de qué equipos es y con qué rol).
3. **Un equipo podrá tener varios workspaces más adelante**; por ahora 1.
4. **TTL de invitaciones: 7 días**. Largo para que un admin invite el lunes y la persona se conecte el viernes; corto para que un código filtrado en logs/screenshots no sea una llave permanente.

## `validar_nombre_equipo`

Normaliza y valida el nombre. **Función pura** (no toca disco ni red); la usan tanto `MemTeamStore` como `PgTeamStore`.

```python
def validar_nombre_equipo(nombre: str) -> str:
    """Devuelve la forma canónica (trim + run de espacios interno colapsado).
    Levanta TeamError con un mensaje legible si no pasa.
    """
```

Reglas:

| Regla | Por qué |
|---|---|
| 1-40 chars | Cabe en TopBar/Hub sin truncar |
| Trim + colapsa espacios contiguos | Anti-suplantación visual ("Ana" vs "Ana ") |
| Sin caracteres de control (`\x00`-`\x1F`, `\x7F`) | Rompen UI/logs |
| Sin zero-width / bidi-override Unicode | Anti-suplantación visual |
| Sin `<`, `>` | Defensa en profundidad (HTML) |

Acepta acentos, espacios internos, puntuación normal: queremos "Equipo de Ana 2", "Founders' Workspace", "ML/CV", etc.

La regla es deliberadamente conservadora: ante la duda, inválido. El admin que quiso poner `"Equipo <script>"` recibe un error claro y prueba con `"Equipo de Ana"` — no duele.

## Estructura interna de `MemTeamStore`

```python
class MemTeamStore:
    _equipos: dict[str, dict]              # id → {id, nombre, creador, plan, stripe_subscription_id}
    _miembros: dict[str, dict[str, str]]   # team_id → {username: rol}
    _invites: dict[str, dict]              # code → {team_id, creado_por, usado_por, expires_at}
    _lock: asyncio.Lock                    # Para tramos check-then-set
```

El `_lock` es `asyncio.Lock` (no `threading.Lock`) porque toda la API es async. Cubre tramos críticos como `redimir`:

```python
async def redimir(self, code, usuario):
    async with self._lock:
        inv = self._invites.get(code)
        if inv is None or inv["usado_por"] is not None:
            return None
        # check expiración, plan, miembro...
        inv["usado_por"] = u
        self._miembros[tid][u] = "member"
```

Sin el lock, dos intentos concurrentes con el mismo código podían pasar ambos el check y ambos consumir el código (BACKEND-AUDIT-0237).

## Métodos (`TeamStorePort`)

### Equipos

```python
crear_equipo(nombre, creador) -> dict
    # Devuelve {id, nombre}. El creador queda como admin.
    # Genera un id corto (4 bytes hex = 8 chars).

equipo(team_id) -> dict | None
    # {id, nombre, plan} o None.

plan(team_id) -> str  # "free" o "premium" (default "free")
set_plan(team_id, plan) -> None  # Fuera de banda (admin/billing).

actualizar_suscripcion(team_id, plan, sub_id) -> None
    # Setea plan + stripe_subscription_id atómico.
    # Lo usa el webhook: alta = (premium, "sub_..."), baja = (free, "").

suscripcion(team_id) -> str  # "sub_..." o "" si free / sin suscripción.

contar_miembros(team_id) -> int  # = asientos a cobrar.

todos() -> list[dict]  # Panel admin: todos los equipos con plan + #miembros.

equipos_de(usuario) -> list[dict]
    # Para el Lobby del usuario.
    # Incluye rol, plan, miembros (para el botón de upgrade del Hub).

borrar(team_id) -> bool
    # Capa 23. CASCADE en FK barre team_members/invites/ownership/proposals.
    # NO toca el workspace en disco (el operador hace `rm` aparte si quiere).
    # NO cancela la suscripción de Stripe (desde el dashboard del operador).
```

### Membresía

```python
es_miembro(team_id, usuario) -> bool
rol(team_id, usuario) -> str | None  # "admin" | "member" | None
miembros(team_id) -> list[dict]      # [{usuario, rol}, ...] ordenado.
```

### Invitaciones

```python
crear_invitacion(team_id, por_usuario) -> str
    # Solo el admin. Devuelve un código `token_urlsafe(9)`.
    # expires_at = now + 7 días.

redimir(code, usuario) -> dict | None
    # Une al equipo (rol member) si el código es válido.
    # Atómico (lock interno).
    # Verifica:
    #   - código existe y no usado
    #   - código no expirado (BACKEND-AUDIT-0214)
    #   - equipo no fue borrado entre medio
    #   - plan permite sumar un miembro nuevo (capa 22)
    # Si rebasa el plan: TeamError (NO consume el código → reintentás tras upgrade).
```

## ID del equipo (`_id_equipo()`)

```python
def _id_equipo() -> str:
    return secrets.token_hex(4)  # 8 chars hex
```

Id corto y estable, independiente del nombre. El nombre puede repetir o cambiar; el id no. 4 bytes hex = colisión despreciable a esta escala (5-50 devs).

`MemTeamStore.crear_equipo` reintenta si por casualidad colisiona; `PgTeamStore.crear_equipo` tiene un tope de 16 reintentos (BACKEND-AUDIT-0179) para no congelarse si un bug en `_id_equipo` siempre devuelve el mismo.

## TTL de invitaciones (capa nueva)

Antes las invitaciones no caducaban. El usuario lo vio como un riesgo: un código filtrado en un screenshot de un chat queda activo para siempre.

**Fix BACKEND-AUDIT-0214**: TTL = 7 días.

- `INVITE_TTL_DAYS = 7` es el único lugar de verdad.
- `MemTeamStore` lo aplica con `datetime.now(UTC) + timedelta(days=7)`; chequea en `redimir`.
- `PgTeamStore` usa SQL `now() + interval '7 days'` y chequea expirada dentro del `FOR UPDATE` (atómico).
- Distingue "expirada" de "no existe" / "ya usada" en el mensaje al usuario:
  - Expirada → `TeamError("esta invitación expiró — pedile al admin una nueva")`
  - No existe / usada → `None` (UX del lobby muestra "código inválido").

## Cap de devs por plan

Plan free: 5 devs por equipo. Plan premium: INF.

`redimir` chequea ANTES de consumir el código:

```python
m = self._miembros.get(tid, {})
if u not in m and not permite_miembro(equipo["plan"], len(m)):
    raise TeamError(
        f"este equipo llegó al límite del plan free "
        f"({limites('free')['max_devs']} devs) — premium para sumar más"
    )
```

Si rebasa, el código NO se consume → el invitado puede reintentar tras el upgrade. Mensaje claro de plan, no "código inválido".

## Por qué `MemTeamStore` vive en `domain/`

Decisión deliberada. `MemTeamStore` NO es un adapter externo — es la implementación de referencia que define la semántica que `PgTeamStore` debe replicar. La regla "Pg cumple la misma superficie async que Mem" es lo que valida el contrato.

Si en el futuro hay un `RedisTeamStore`, `SqliteTeamStore`, etc., esos sí van a `adapters/outbound/`. El Mem se queda con el dominio.

## Cobro por asiento (capa 31)

Cuando alguien redime una invitación en un equipo premium:

1. `MemTeamStore.redimir` (o `PgTeamStore.redimir`) lo agrega a `team_members`.
2. El server (`adapters/inbound/websocket/seats.py:disparar_ajuste`) corre en background:
   - Lee `teams.suscripcion(team_id)` para el `sub_...`.
   - Lee `teams.contar_miembros(team_id)` para el conteo nuevo.
   - POST a Stripe para actualizar la cantidad del subscription item.
3. Stripe prorratea automáticamente.

Lock `_asientos_locks[team_id]` por equipo: dos miembros entrando casi a la vez no se pisan el conteo.

Si `STRIPE_SECRET_KEY` no está seteado (modo dev sin billing) → el ajuste se omite silencioso.
