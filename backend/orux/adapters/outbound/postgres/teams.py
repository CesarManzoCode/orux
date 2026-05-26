"""Adaptador Postgres del store de equipos. MISMA superficie async que
`MemTeamStore` (mismos nombres, contratos y excepciones): el server no sabe
con cuál habla. NO verificable en el sandbox (sin internet/DB); se ejercita
en el VPS cuando el server lo adopte (paso 3). SQL estándar, parametrizado
($1…), transacciones para lo que debe ser atómico.
"""

from __future__ import annotations

import logging

from orux.domain.identity.store import normalizar
from orux.domain.plans import PLAN_DEFECTO, limites, permite_miembro
from orux.domain.teams.store import (
    TeamError,
    _codigo,
    _id_equipo,
    validar_nombre_equipo,
)

logger = logging.getLogger(__name__)


class PgTeamStore:
    def __init__(self, db) -> None:
        self._db = db  # orux.db.Database

    async def crear_equipo(self, nombre: str, creador: str) -> dict:
        # Misma validación que MemTeamStore (un único validador): trim,
        # colapsa espacios, rechaza control/invisibles/HTML/excesivos.
        nombre = validar_nombre_equipo(nombre)
        creador = normalizar(creador)
        async with self._db.tx() as con:
            tid = _id_equipo()
            # Reintenta ante el caso (improbable) de id repetido, con tope.
            # BACKEND-AUDIT-0179: sin tope, un bug en `_id_equipo` (siempre el
            # mismo) congelaba la transacción.
            for _ in range(16):
                if not await con.fetchval(
                    "SELECT 1 FROM teams WHERE id=$1", tid
                ):
                    break
                tid = _id_equipo()
            else:
                raise TeamError("no se pudo generar id de equipo único")
            await con.execute(
                "INSERT INTO teams (id, nombre, creador) VALUES ($1,$2,$3)",
                tid, nombre, creador,
            )
            await con.execute(
                "INSERT INTO team_members (team_id, username, rol) "
                "VALUES ($1,$2,'admin')",
                tid, creador,
            )
        return {"id": tid, "nombre": nombre}

    async def equipo(self, team_id: str) -> dict | None:
        r = await self._db.fetchrow(
            "SELECT id, nombre, plan FROM teams WHERE id=$1", team_id
        )
        return (
            {"id": r["id"], "nombre": r["nombre"], "plan": r["plan"]}
            if r else None
        )

    async def plan(self, team_id: str) -> str:
        """Capa 22: plan del equipo. NULL/sin equipo -> free."""
        p = await self._db.fetchval(
            "SELECT plan FROM teams WHERE id=$1", team_id
        )
        return p or PLAN_DEFECTO

    async def set_plan(self, team_id: str, plan: str) -> None:
        """Fuera de banda (admin/futuro billing). El esqueleto solo lee.

        Loguea el resultado del UPDATE (`UPDATE N`) para que un operador a
        las 3am pueda confirmar que "el plan del equipo cambió" tuvo efecto
        real y no fue un no-op silencioso (id que ya no existe, etc.).
        Sólo observabilidad: no cambia el comportamiento existente.
        """
        res = await self._db.execute(
            "UPDATE teams SET plan=$2 WHERE id=$1", team_id, plan
        )
        logger.info(
            "PgTeamStore.set_plan: team=%s plan=%s -> %s",
            team_id, plan, res,
        )

    async def actualizar_suscripcion(
        self, team_id: str, plan: str, subscription_id: str
    ) -> None:
        """Capa 31: plan + id de la suscripción de Stripe en un solo UPDATE
        (atómico). El webhook lo usa: alta -> (premium, "sub_..."), baja ->
        (free, ""). `""` se guarda como NULL (la suscripción ya no existe).

        Loguea para diagnóstico del cobro: si un equipo "no aparece premium
        después de pagar", el log dice si el UPDATE corrió y a qué row tocó.
        El `subscription_id` NO es secreto (Stripe lo emite y lo usa el
        operator desde el dashboard); el resto sí (clave API) ya se omite.
        """
        res = await self._db.execute(
            "UPDATE teams SET plan=$2, stripe_subscription_id=$3 WHERE id=$1",
            team_id, plan, subscription_id or None,
        )
        logger.info(
            "PgTeamStore.actualizar_suscripcion: team=%s plan=%s sub=%s -> %s",
            team_id, plan, subscription_id or "<none>", res,
        )

    async def suscripcion(self, team_id: str) -> str:
        """Capa 31: id de la suscripción de Stripe del equipo; "" si NULL o
        el equipo no existe (el ajuste de asientos lo omite en ese caso)."""
        s = await self._db.fetchval(
            "SELECT stripe_subscription_id FROM teams WHERE id=$1", team_id
        )
        return s or ""

    async def contar_miembros(self, team_id: str) -> int:
        """Capa 31: cantidad de miembros = asientos que se cobran."""
        n = await self._db.fetchval(
            "SELECT count(*) FROM team_members WHERE team_id=$1", team_id
        )
        return int(n or 0)

    async def todos(self) -> list[dict]:
        """Capa 23: TODOS los equipos con su plan y #miembros (operador)."""
        rows = await self._db.fetch(
            "SELECT t.id, t.nombre, t.plan, "
            "count(m.username) AS miembros "
            "FROM teams t LEFT JOIN team_members m ON m.team_id = t.id "
            "GROUP BY t.id, t.nombre, t.plan ORDER BY t.nombre"
        )
        return [
            {"id": r["id"], "nombre": r["nombre"], "plan": r["plan"],
             "miembros": r["miembros"]}
            for r in rows
        ]

    async def equipos_de(self, usuario: str) -> list[dict]:
        # Incluye `t.plan` (capa 30) y `miembros` (capa 31, cobro por
        # asiento): el Hub usa el plan para el badge/upgrade y el conteo
        # para mostrar los asientos. Misma forma que MemTeamStore.equipos_de.
        # El conteo es una subconsulta correlacionada: pocos equipos por
        # usuario, índice idx_members_user — barato.
        rows = await self._db.fetch(
            "SELECT t.id, t.nombre, t.plan, m.rol, "
            "(SELECT count(*) FROM team_members mm WHERE mm.team_id = t.id) "
            "AS miembros "
            "FROM team_members m JOIN teams t ON t.id = m.team_id "
            "WHERE m.username=$1 ORDER BY t.nombre",
            normalizar(usuario),
        )
        return [
            {"id": r["id"], "nombre": r["nombre"], "rol": r["rol"],
             "plan": r["plan"], "miembros": int(r["miembros"] or 0)}
            for r in rows
        ]

    async def es_miembro(self, team_id: str, usuario: str) -> bool:
        return bool(await self._db.fetchval(
            "SELECT 1 FROM team_members WHERE team_id=$1 AND username=$2",
            team_id, normalizar(usuario),
        ))

    async def rol(self, team_id: str, usuario: str) -> str | None:
        return await self._db.fetchval(
            "SELECT rol FROM team_members WHERE team_id=$1 AND username=$2",
            team_id, normalizar(usuario),
        )

    async def miembros(self, team_id: str) -> list[dict]:
        rows = await self._db.fetch(
            "SELECT username, rol FROM team_members "
            "WHERE team_id=$1 ORDER BY username",
            team_id,
        )
        return [{"usuario": r["username"], "rol": r["rol"]} for r in rows]

    async def borrar(self, team_id: str) -> bool:
        # Consola de operador (capa 23): borra el equipo. CASCADE en las
        # FK barre team_members, invites, ownership y proposals automático
        # (ver db/schema.sql). NO toca disco — el workspace en
        # /data/ws/<tid>/ vive aparte; el caller decide si lo borra también.
        # NO cancela la suscripción de Stripe — eso se hace desde el
        # dashboard del operador (acá solo borramos lo nuestro).
        v = await self._db.fetchval(
            "DELETE FROM teams WHERE id=$1 RETURNING id", team_id,
        )
        return v is not None

    async def crear_invitacion(self, team_id: str, por_usuario: str) -> str:
        if not await self._db.fetchval("SELECT 1 FROM teams WHERE id=$1", team_id):
            raise TeamError("ese equipo no existe")
        if await self.rol(team_id, por_usuario) != "admin":
            raise TeamError("solo el admin del equipo puede invitar")
        async with self._db.tx() as con:
            code = _codigo()
            while await con.fetchval("SELECT 1 FROM invites WHERE code=$1", code):
                code = _codigo()
            # BACKEND-AUDIT-0214 (fix): TTL 7d explícito. La columna también
            # tiene DEFAULT por defensa en profundidad, pero seteamos acá
            # para que el código documente la regla y un cambio futuro de
            # default no se nos cuele en silencio.
            await con.execute(
                "INSERT INTO invites (code, team_id, creado_por, expires_at) "
                "VALUES ($1,$2,$3, now() + interval '7 days')",
                code, team_id, normalizar(por_usuario),
            )
        return code

    async def redimir(self, code: str, usuario: str) -> dict | None:
        u = normalizar(usuario)
        async with self._db.tx() as con:
            # BACKEND-AUDIT-0214 (fix): el chequeo de expiración va en SQL
            # para que sea atómico con el FOR UPDATE. `expirada` es un bool
            # derivado: NULL en `expires_at` significa "row pre-fix sin
            # backfill" → tratamos como NO expirada (el backfill del
            # esquema cubre eso al re-deployar). Distinguir expirada de
            # "no existe" deja que la UX del lobby diga al invitado por
            # qué falló (TeamError vs None).
            inv = await con.fetchrow(
                "SELECT team_id, usado_por, "
                "  (expires_at IS NOT NULL AND expires_at <= now()) AS expirada "
                "FROM invites WHERE code=$1 FOR UPDATE",
                code,
            )
            if inv is None or inv["usado_por"] is not None:
                return None
            if inv["expirada"]:
                raise TeamError(
                    "esta invitación expiró — pedile al admin una nueva"
                )
            tid = inv["team_id"]
            t = await con.fetchrow(
                "SELECT id, nombre, plan FROM teams WHERE id=$1", tid
            )
            if t is None:  # equipo borrado entre medio
                return None
            # Capa 22: tope de devs del plan. Dentro de la tx: si rechaza,
            # rollback => la invitación NO se consume (reintentás tras el
            # upgrade). Solo bloquea si suma miembro nuevo.
            ya = await con.fetchval(
                "SELECT 1 FROM team_members WHERE team_id=$1 AND username=$2",
                tid, u,
            )
            if not ya:
                n = await con.fetchval(
                    "SELECT count(*) FROM team_members WHERE team_id=$1", tid
                )
                if not permite_miembro(t["plan"], n):
                    raise TeamError(
                        f"este equipo llegó al límite del plan free "
                        f"({limites('free')['max_devs']} devs) — premium "
                        f"para sumar más"
                    )
            await con.execute(
                "UPDATE invites SET usado_por=$1, usado_at=now() WHERE code=$2",
                u, code,
            )
            await con.execute(
                "INSERT INTO team_members (team_id, username, rol) "
                "VALUES ($1,$2,'member') ON CONFLICT DO NOTHING",
                tid, u,
            )
            return {"id": t["id"], "nombre": t["nombre"]}
