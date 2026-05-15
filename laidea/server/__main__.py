"""Punto de entrada: `python -m laidea.server` o `laidea-server`."""

from __future__ import annotations

import asyncio
import logging

from .sync import SyncServer


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    asyncio.run(SyncServer().run())


if __name__ == "__main__":
    main()
