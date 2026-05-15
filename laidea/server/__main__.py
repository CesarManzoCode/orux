"""Punto de entrada: `python -m laidea.server` o `laidea-server`.

Aquí —y solo aquí— se cablea la persistencia real (capa 3). El `SyncServer`
no sabe de directorios por sí mismo: recibe un `DiskStorage` inyectado. Eso
mantiene los tests arrancando en memoria y deja la decisión de "dónde se
guarda" en un único lugar visible.

**Por qué el directorio por defecto está FUERA del repo** (`~/.laidea/...`):
en desarrollo el cliente se sirve con un servidor estático que vigila la
carpeta del proyecto y recarga el navegador ante cualquier cambio de archivo
(p. ej. Live Server). Si la persistencia escribiera dentro del repo, cada vez
que alguien crea un archivo o se aprueba un cambio, el watcher recargaría la
página, se caería el WebSocket y el cliente volvería con otra identidad —
perdiendo su ownership. Sacar el estado de ejecución del árbol vigilado mata
ese ciclo de raíz, sin depender de configurar el editor de cada quien.

Cuando llegue la integración con Git (capa final) esa capa decidirá su propia
ubicación dentro del repo del usuario; ese es su problema, no el del runtime.

Se puede sobreescribir con la variable de entorno `LAIDEA_DATA`. Si la
apuntas dentro del repo, acuérdate de excluirla del watcher (en `.gitignore`
ya está `workspace_data/`).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from ..state import DiskStorage
from .sync import SyncServer

# Estado de ejecución, fuera del árbol del proyecto a propósito (ver docstring).
DIRECTORIO_POR_DEFECTO = Path.home() / ".laidea" / "workspace"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    env = os.environ.get("LAIDEA_DATA")
    root = Path(env) if env else DIRECTORIO_POR_DEFECTO
    storage = DiskStorage(root)
    logging.getLogger(__name__).info("workspace persistido en %s", storage.root)
    asyncio.run(SyncServer(storage=storage).run())


if __name__ == "__main__":
    main()
