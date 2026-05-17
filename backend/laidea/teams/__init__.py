"""Dominio de equipos (capa 15: sistema multi-equipo).

Antes laidea era mono-tenant: un workspace global, un admin global. El
usuario pidió que sea un sistema de verdad: varios equipos que no se
enteran del otro. Esta es la pieza pura de "quién es de qué equipo y quién
manda ahí" — sin red, sin DB, sin Postgres importado.

Mismo patrón de inyección que el resto del stack: `MemTeamStore` es la
implementación en memoria (tests, y este sandbox sin internet). El
adaptador Postgres (`PgTeamStore`, paso 2) implementará EXACTO esta misma
superficie, así la lógica multi-tenant se prueba 100% acá y lo único no
verificable localmente es el I/O real de Postgres.
"""

from .pg import PgTeamStore
from .store import MemTeamStore, TeamError

__all__ = ["MemTeamStore", "PgTeamStore", "TeamError"]
