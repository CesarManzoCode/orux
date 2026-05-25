"""Adapters: implementaciones concretas de los Ports definidos en `orux.ports`.

Cada subpaquete agrupa adapters por tecnología:

- `adapters.json`: archivos JSON locales (modo dev sin Postgres).

Los adapters Postgres viven en `orux.db.stores` (histórico) y `orux.teams.pg`;
no se movieron acá para evitar churn masivo de imports. Cumplen los Ports
igual; ver `tests/test_ports_contract.py` para la verificación estructural.
"""
