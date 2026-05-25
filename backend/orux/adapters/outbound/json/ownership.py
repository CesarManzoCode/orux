"""`JsonOwnershipStore`: persistencia del mapa ownership en un archivo JSON.

Modo dev / tests sin Postgres. La lógica de atomicidad / permisos /
validación es la que vivía inline en `state.Ownership` antes del refactor
hex; acá queda encapsulada como adapter del `OwnershipStorePort`.

Single-team por diseño: el modo dev tiene UN archivo. El `team_id` del
contrato del Port se acepta pero se IGNORA (no hay subdirectorio por equipo).
Multi-team JSON sería otro adapter; por ahora sólo Postgres soporta multi.

Hardening conservado del original (BACKEND-AUDIT-006x):
- Tmp único con pid+uuid: no colisiona entre corutinas del mismo proceso.
- Permisos 0600: el ownership no tiene secretos pero es estado autoritativo.
- JSON no-dict se rechaza al cargar; paths peligrosos se filtran (`path_seguro`).
- fsync antes del replace: durabilidad real ante corte de luz.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

from orux.domain.state.paths import path_seguro


class JsonOwnershipStore:
    """Implementa `OwnershipStorePort` sobre un archivo JSON local.

    El `team_id` se ignora: un store = un archivo = un equipo (modo dev).
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    async def cargar(self, team_id: str) -> dict[str, str]:
        del team_id  # ignorado a propósito (single-team)
        return await asyncio.to_thread(self._cargar_sync)

    def _cargar_sync(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (ValueError, OSError, TypeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            k: v for k, v in data.items()
            if isinstance(k, str) and isinstance(v, str) and path_seguro(k)
        }

    async def guardar(
        self, team_id: str, owners: dict[str, str],
    ) -> None:
        del team_id  # ignorado a propósito (single-team)
        await asyncio.to_thread(self._guardar_sync, owners)

    def _guardar_sync(self, owners: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        sufijo = f".{os.getpid()}.{uuid.uuid4().hex}.tmp"
        tmp = self._path.with_suffix(self._path.suffix + sufijo)
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(
                        owners, f, indent=2, sort_keys=True, ensure_ascii=False,
                    )
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                raise
            os.replace(tmp, self._path)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
