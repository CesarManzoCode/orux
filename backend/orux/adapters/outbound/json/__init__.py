"""Adapters JSON: persistencia en archivos locales para modo dev / tests.

Encapsulan la lógica que antes vivía inline en `state.Ownership` y
`identity.UserStore` (atomicidad, permisos 0600, tmp con pid+uuid, validación
estructural al cargar). Sacarla del dominio permite que `Ownership` /
`UserStore` sean memoria pura, testeables sin disco, y que el caller
inyecte la persistencia que quiera.

Async para alinear con `OwnershipStorePort` / `UserStorePort` (los Pg* son
async nativos): el IO sync se envuelve con `asyncio.to_thread` para no
bloquear el loop.
"""

from .ownership import JsonOwnershipStore
from .users import JsonUserStore

__all__ = ["JsonOwnershipStore", "JsonUserStore"]
