"""Punto de entrada: `python -m laidea.server` o `laidea-server`.

Aquí —y solo aquí— se cablea la persistencia real (capa 3). El `SyncServer`
no sabe de directorios por sí mismo: recibe un `DiskStorage` inyectado. Eso
mantiene los tests arrancando en memoria y deja la decisión de "dónde se
guarda" en un único lugar visible.

El directorio se puede sobreescribir con la variable de entorno
`LAIDEA_DATA`; por defecto es `workspace_data/` en el directorio donde se
arranca el server. Está en `.gitignore`: es estado de ejecución, no código.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from ..state import DiskStorage
from .sync import SyncServer


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    root = Path(os.environ.get("LAIDEA_DATA", "workspace_data"))
    storage = DiskStorage(root)
    logging.getLogger(__name__).info("workspace persistido en %s", storage.root)
    asyncio.run(SyncServer(storage=storage).run())


if __name__ == "__main__":
    main()
