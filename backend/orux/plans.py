"""Planes y sus límites — el esqueleto del freemium (capa 22).

Decisiones DECRETADAS con el usuario (no re-litigar): la espina es **tiers
por escala**, no un medidor que se agota (en coordinación continua eso se
lee como bait-and-switch y mata el "que vean el valor total"). El free es
PERMANENTE y orux funciona de verdad ahí: no se tiera la tesis, se tieran
escala/profundidad alrededor. Los únicos límites del free son de
escala/recurso (se sienten justos: "creciste, pagás"), nunca de capacidad
("te quitamos lo bueno").

Acá viven los límites como DATO central, no como `if`s dispersos: agregar
un plan o mover un número es una línea, y el resto del código pregunta
"¿este plan permite X?" sin saber números. Esto es el esqueleto; las
features premium (impacto transitivo, distribución de conocimiento,
integraciones) se enchufan después contra estos mismos límites.

`INF` = sin límite (premium). El `plan` por equipo lo setea algo FUERA de
banda (DB/admin/futuro billing); este módulo solo lo interpreta.
"""

from __future__ import annotations

INF = float("inf")

# clave de plan -> límites. free = el target declarado (founders 2-3, OSS
# que empieza) con TODO funcionando; 5 devs lo decidió el usuario.
PLANES: dict[str, dict] = {
    "free": {
        "max_devs": 5,          # tope de miembros por equipo (enforced)
        "max_workspaces": 1,    # modelado; multi-workspace aún no existe
        "max_langs": 2,         # LSP activos a la vez (lever de costo real)
        "impacto": "directo",   # premium: "transitivo" + cross-repo
        "jvm": False,           # Java/Kotlin (servers JVM caros) = premium
        "warm": False,          # idle-eviction agresivo; premium siempre tibio
        "conocimiento": False,  # distribución de conocimiento = premium
        # Capa 26: rename seguro coordinado. Free = solo el aviso de texto
        # accionable ("se renombró X→Y, actualizá los usos"); premium = la
        # propagación automática como propuesta capa 4 (1-clic aprobar/
        # rechazar). Free real (sabe qué y dónde), premium automatiza la mano.
        "rename": False,
    },
    "premium": {
        "max_devs": INF,
        "max_workspaces": INF,
        "max_langs": INF,
        "impacto": "transitivo",
        "jvm": True,
        "warm": True,
        "conocimiento": True,
        "rename": True,
    },
}

# Plan por defecto de un equipo nuevo. El free es la puerta de entrada.
PLAN_DEFECTO = "free"


def limites(plan: str) -> dict:
    """Límites del plan; si el plan es desconocido cae a free (nunca premium
    por error: fallar hacia el lado seguro/barato)."""
    return PLANES.get(plan, PLANES["free"])


def permite_miembro(plan: str, miembros_actuales: int) -> bool:
    """¿Puede entrar UN miembro más? (`miembros_actuales` = cuántos hay YA)."""
    return miembros_actuales < limites(plan)["max_devs"]


def permite_lenguaje(plan: str, langs_activos: int) -> bool:
    """¿Puede activarse UN lenguaje LSP más? (`langs_activos` = los que ya
    tienen sesión). Al exceder, el análisis degrada a tree-sitter/coarse:
    NO se rompe, solo no se paga el LSP del lenguaje extra."""
    return langs_activos < limites(plan)["max_langs"]


def permite_workspace(plan: str, workspaces_actuales: int) -> bool:
    """Modelado para cuando exista multi-workspace (hoy 1/equipo por
    arquitectura). Hook listo; no se enforca lo que aún no se puede crear."""
    return workspaces_actuales < limites(plan)["max_workspaces"]


def permite_jvm(plan: str) -> bool:
    return limites(plan)["jvm"]


def permite_rename(plan: str) -> bool:
    """Capa 26: ¿este plan aplica el rename automático (propuesta capa 4) o
    solo da el aviso de texto? Free = solo texto; premium = lo aplica."""
    return limites(plan)["rename"]


def impacto_modo(plan: str) -> str:
    """'directo' (free) | 'transitivo' (premium). El motor de impacto
    transitivo es feature premium futura; el flag ya vive acá."""
    return limites(plan)["impacto"]
