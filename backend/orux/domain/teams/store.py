"""Almacén de equipos, membresía e invitaciones — implementación en memoria.

Reglas del dominio (decididas con el usuario):

- El que **crea** un equipo es su `admin`. El admin invita; los demás se
  unen redimiendo un código de un solo uso.
- Cualquiera puede tener cuenta, pero sin pertenecer a un equipo NO ve nada
  (eso lo hace cumplir el server: este store sólo dice de qué equipos es y
  con qué rol).
- Un equipo podrá tener varios workspaces más adelante; por ahora 1.

La interfaz es **async**: el server es asyncio y el adaptador Postgres
(`PgTeamStore`) es async nativo. `MemTeamStore` también es async (devuelve
al instante) para que server y tests usen UNA sola superficie. Es la verdad
para los tests y para este sandbox sin internet/DB.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from ..identity.store import normalizar
from ..plans import PLAN_DEFECTO, limites, permite_miembro

# BACKEND-AUDIT-0214 (fix): TTL de invitaciones, único lugar de verdad
# (pg.py usa el mismo número inline en SQL — si cambia, cambian los dos).
# 7 días es el balance del usuario: largo para que un admin invite el lunes
# y la persona se conecte el viernes; corto para que un código filtrado en
# logs/screenshots no sea una llave permanente.
INVITE_TTL_DAYS = 7


class TeamError(ValueError):
    """Error de dominio (nombre vacío, no-admin invitando, etc.). El server
    lo traduce a un mensaje para el cliente, no a una caída."""


# Nombre de equipo: límites del que la UX se queda dentro de un chrome IDE
# (no es un editor de texto). 40 chars caben en TopBar/Hub sin truncar; cero
# HTML/control chars/invisibles porque viajan por logs/JSON/Postgres/UI a
# todo el equipo. La regla es deliberadamente conservadora: ante la duda,
# inválido. El admin que quiso poner "Equipo `<script>`" recibe un error
# claro y prueba con "Equipo de Ana" — no es restricción que duela.
_NOMBRE_MIN = 1
_NOMBRE_MAX = 40
# Mismos invisibles que `paths.py`: zero-width y bidi-override sirven para
# que dos equipos "se vean iguales" cuando no lo son (suplantación visual).
_NOMBRE_INVISIBLES = {
    "​", "‌", "‍", "‎", "‏",
    "‪", "‫", "‬", "‭", "‮",
    "⁦", "⁧", "⁨", "⁩", "﻿",
}
# Caracteres prohibidos: los que rompen al pintarlos como texto en logs/UI
# (`<`, `>`) o que delatan a alguien jugando con HTML/JSON. NO baneamos
# acentos, espacios internos ni puntuación normal: queremos "Equipo de
# Ana 2", "Founders' Workspace", "ML/CV" etc.
_NOMBRE_PROHIBIDOS = set("<>")


def validar_nombre_equipo(nombre: str) -> str:
    """Normaliza y valida un nombre de equipo. Devuelve la forma canónica
    (trim + run de espacios interno colapsado). Lanza `TeamError` con un
    mensaje legible si no pasa. Es PURA: no toca disco ni red — la usan
    tanto el store en memoria como el adaptador Postgres."""
    if not isinstance(nombre, str):
        raise TeamError("nombre de equipo inválido")
    n = nombre.strip()
    # Colapsa runs de espacios internos: "  A   B  " -> "A B". Espacios
    # contiguos son fuente típica de "dos equipos con el mismo nombre" donde
    # uno tiene un espacio doble invisible.
    if "  " in n:
        partes = [p for p in n.split(" ") if p]
        n = " ".join(partes)
    if len(n) < _NOMBRE_MIN:
        raise TeamError("el nombre del equipo no puede estar vacío")
    if len(n) > _NOMBRE_MAX:
        raise TeamError(
            f"el nombre del equipo es muy largo (máximo {_NOMBRE_MAX} caracteres)"
        )
    for c in n:
        co = ord(c)
        if co < 0x20 or co == 0x7F:
            raise TeamError("el nombre del equipo tiene caracteres de control")
        if c in _NOMBRE_INVISIBLES:
            raise TeamError("el nombre del equipo tiene caracteres invisibles")
        if c in _NOMBRE_PROHIBIDOS:
            raise TeamError("usa solo letras, números y puntuación normal")
    return n


def _id_equipo() -> str:
    # Id corto y estable, independiente del nombre (el nombre puede repetir
    # o cambiar; el id no). 8 hex = colisión despreciable a esta escala.
    return secrets.token_hex(4)


def _codigo() -> str:
    return secrets.token_urlsafe(9)


class MemTeamStore:
    def __init__(self, backend: object | None = None) -> None:
        # `backend` se mantiene como parámetro inactivo para compat con
        # callers viejos; el adaptador Postgres es PgTeamStore. Aceptamos
        # el kwarg sin usarlo y NO almacenamos para no inducir bugs.
        del backend
        self._equipos: dict[str, dict] = {}            # id -> {id, nombre, creador}
        self._miembros: dict[str, dict[str, str]] = {} # team_id -> {usuario: rol}
        self._invites: dict[str, dict] = {}            # code -> {team_id, creado_por, usado_por}
        # Lock interno para tramos check-then-set (BACKEND-AUDIT-0237 / -0181).
        # `asyncio.Lock` porque la API es async; el caller no necesita saber.
        import asyncio as _asyncio  # noqa: PLC0415
        self._lock = _asyncio.Lock()

    # --- Equipos ---

    async def crear_equipo(self, nombre: str, creador: str) -> dict:
        """Crea un equipo; `creador` queda como admin. Devuelve {id, nombre}."""
        # `validar_nombre_equipo` normaliza (trim + colapsa espacios) y rechaza
        # control/invisibles/HTML/excesivos. El error que levanta YA tiene
        # mensaje legible para el cliente — no traducimos.
        nombre = validar_nombre_equipo(nombre)
        creador = normalizar(creador)
        tid = _id_equipo()
        while tid in self._equipos:  # paranoia: regenerar ante colisión
            tid = _id_equipo()
        self._equipos[tid] = {
            "id": tid, "nombre": nombre, "creador": creador,
            "plan": PLAN_DEFECTO,  # capa 22: free es la puerta de entrada
            # capa 31: id de la suscripción de Stripe (cobro por asiento).
            # "" hasta que el equipo pague; el webhook lo rellena.
            "stripe_subscription_id": "",
        }
        self._miembros[tid] = {creador: "admin"}
        return {"id": tid, "nombre": nombre}

    async def equipo(self, team_id: str) -> dict | None:
        e = self._equipos.get(team_id)
        return (
            {"id": e["id"], "nombre": e["nombre"], "plan": e["plan"]}
            if e else None
        )

    async def plan(self, team_id: str) -> str:
        """Plan del equipo (capa 22). Desconocido/sin equipo -> free
        (lado barato/seguro)."""
        e = self._equipos.get(team_id)
        return e["plan"] if e else PLAN_DEFECTO

    async def set_plan(self, team_id: str, plan: str) -> None:
        """Setea el plan FUERA de banda (admin/DB/futuro billing). El
        esqueleto solo lo lee; esto es el punto de enganche del pago."""
        if team_id in self._equipos:
            self._equipos[team_id]["plan"] = plan

    async def actualizar_suscripcion(
        self, team_id: str, plan: str, subscription_id: str
    ) -> None:
        """Capa 31: setea el plan Y el id de la suscripción de Stripe a la
        vez. Lo usa el webhook: el alta deja `(premium, "sub_...")`; la
        baja deja `(free, "")` — el `""` limpia el id porque la suscripción
        dejó de existir. Distinto de `set_plan` (el cambio MANUAL del
        operador, que no toca la suscripción)."""
        e = self._equipos.get(team_id)
        if e is not None:
            e["plan"] = plan
            e["stripe_subscription_id"] = subscription_id or ""

    async def suscripcion(self, team_id: str) -> str:
        """Capa 31: id de la suscripción de Stripe del equipo. `""` si no
        tiene (equipo free, o premium puesto a mano por el operador sin
        suscripción real) — el ajuste de asientos lo omite en ese caso."""
        e = self._equipos.get(team_id)
        return (e.get("stripe_subscription_id") or "") if e else ""

    async def contar_miembros(self, team_id: str) -> int:
        """Capa 31: cuántos miembros tiene el equipo = cuántos asientos se
        le cobran. Es la cantidad que se le pasa a la suscripción de
        Stripe."""
        return len(self._miembros.get(team_id, {}))

    async def todos(self) -> list[dict]:
        """Capa 23: TODOS los equipos (consola de operador). Distinto de
        `equipos_de` (por-usuario): el operador ve la plataforma entera."""
        out = [
            {
                "id": e["id"], "nombre": e["nombre"], "plan": e["plan"],
                "miembros": len(self._miembros.get(tid, {})),
            }
            for tid, e in self._equipos.items()
        ]
        out.sort(key=lambda x: x["nombre"])
        return out

    async def equipos_de(self, usuario: str) -> list[dict]:
        """Equipos del usuario, con su rol y su plan. Vacío = todavía no ve
        nada.

        Incluye `plan` (capa 30): el Hub muestra el plan de cada equipo y
        el botón de upgrade junto a la lista, así que el `LobbyMessage`
        —que se arma con esto— ya lo trae. Es un dato barato de adjuntar
        y evita un round-trip extra del cliente solo para saberlo.

        Incluye también `miembros` (capa 31): el cobro es por asiento, así
        que el Hub muestra cuántos asientos tiene/tendría el equipo."""
        u = normalizar(usuario)
        out = []
        for tid, miembros in self._miembros.items():
            if u in miembros:
                e = self._equipos[tid]
                out.append({
                    "id": tid, "nombre": e["nombre"], "rol": miembros[u],
                    "plan": e["plan"], "miembros": len(miembros),
                })
        out.sort(key=lambda x: x["nombre"])
        return out

    # --- Membresía ---

    async def es_miembro(self, team_id: str, usuario: str) -> bool:
        return normalizar(usuario) in self._miembros.get(team_id, {})

    async def rol(self, team_id: str, usuario: str) -> str | None:
        """'admin' | 'member' | None (no es miembro)."""
        return self._miembros.get(team_id, {}).get(normalizar(usuario))

    async def miembros(self, team_id: str) -> list[dict]:
        return sorted(
            ({"usuario": u, "rol": r} for u, r in self._miembros.get(team_id, {}).items()),
            key=lambda x: x["usuario"],
        )

    async def borrar(self, team_id: str) -> bool:
        # Capa 23: simétrico al PgTeamStore.borrar. Limpia el equipo y todo
        # lo asociado en memoria (miembros + invitaciones). Tests/dev only.
        if team_id not in self._equipos:
            return False
        self._equipos.pop(team_id, None)
        self._miembros.pop(team_id, None)
        self._invites = {
            c: i for c, i in self._invites.items()
            if i["team_id"] != team_id
        }
        return True

    # --- Invitaciones (de un solo uso) ---

    async def crear_invitacion(self, team_id: str, por_usuario: str) -> str:
        """Sólo el admin del equipo invita. Devuelve el código a compartir."""
        if team_id not in self._equipos:
            raise TeamError("ese equipo no existe")
        if await self.rol(team_id, por_usuario) != "admin":
            # Defensa en profundidad: el server ya lo gatea, pero el dominio
            # no deja crear invitaciones a quien no es admin del equipo.
            raise TeamError("solo el admin del equipo puede invitar")
        code = _codigo()
        while code in self._invites:
            code = _codigo()
        self._invites[code] = {
            "team_id": team_id,
            "creado_por": normalizar(por_usuario),
            "usado_por": None,
            # BACKEND-AUDIT-0214: caducidad real. Absoluta (datetime) para
            # que tests/operadores puedan forzar expiración pisando el
            # valor sin tocar el reloj del proceso.
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)
            ),
        }
        return code

    async def redimir(self, code: str, usuario: str) -> dict | None:
        """Une a `usuario` al equipo del código. Devuelve {id, nombre} o None
        si el código no existe o ya se usó. Idempotente si ya era miembro
        (igual consume el código: un código = una persona).

        Lock interno (BACKEND-AUDIT-0237): el check `inv["usado_por"] is None`
        seguido del set `inv["usado_por"] = u` debe ser atómico. Sin esto, dos
        intentos concurrentes con el mismo código podían pasar ambos el
        check y ambos consumir el código.
        """
        async with self._lock:
            inv = self._invites.get(code)
            if inv is None or inv["usado_por"] is not None:
                return None
            # BACKEND-AUDIT-0214: caducidad. Distinguir "expirada" de "no
            # existe" / "ya usada" para que la UX del lobby (`lobby.py`) le
            # diga al invitado por qué — un código expirado es accionable
            # (pedir uno nuevo), un código que no existe es un typo.
            exp = inv.get("expires_at")
            if exp is not None and exp <= datetime.now(timezone.utc):
                raise TeamError(
                    "esta invitación expiró — pedile al admin una nueva"
                )
            u = normalizar(usuario)
            tid = inv["team_id"]
            if tid not in self._equipos:  # equipo borrado entre medio
                return None
            # Capa 22: tope de devs del plan. Solo bloquea si SUMA un miembro
            # nuevo (ya-miembro es idempotente). Se valida ANTES de consumir el
            # código: un equipo lleno no te quema la invitación (reintentás
            # tras el upgrade). Mensaje claro de plan, no "código inválido".
            m = self._miembros.get(tid, {})
            if u not in m and not permite_miembro(
                self._equipos[tid]["plan"], len(m)
            ):
                raise TeamError(
                    f"este equipo llegó al límite del plan free "
                    f"({limites('free')['max_devs']} devs) — premium para "
                    f"sumar más"
                )
            inv["usado_por"] = u
            self._miembros.setdefault(tid, {}).setdefault(u, "member")
            e = self._equipos[tid]
            return {"id": tid, "nombre": e["nombre"]}
