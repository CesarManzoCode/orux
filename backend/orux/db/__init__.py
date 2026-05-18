"""Capa de acceso a Postgres (capa 15, paso 2).

`asyncpg` se importa de forma PEREZOSA (dentro de `Database.conectar`): así
`import orux` no exige tener asyncpg ni un Postgres corriendo. Sin
`ORUX_DB_DSN` el server sigue en JSON/memoria y los tests jamás tocan
esto — la suite corre igual en un sandbox sin internet ni DB.
"""

from .pool import Database

__all__ = ["Database"]
