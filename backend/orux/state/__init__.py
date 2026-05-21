"""Estado autoritativo del server: workspace, presencia, ownership, propuestas.

Re-exporta los tipos que el resto del sistema consume sin importar de
sub-módulos concretos.

Invariantes de concurrencia (importante para futuro):
- `Ownership` lleva su propio `threading.Lock` interno desde el fix de
  BACKEND-AUDIT-0088: claim/asignar/liberar/reset/purgar_usuario son
  atómicos sin que el caller necesite tomar un lock externo.
- `Proposals`, `Workspace` y `Roster` NO tienen lock interno: asumen que el
  caller (SyncServer) coordina con `rt._estado_lock` para tramos
  read-modify-write. La presencia (`Roster.mover`, `Roster.quitar`) se
  llama desde el hot path sin lock; son operaciones O(1) sobre un dict
  por equipo y no chocan con otros mensajes (cada conexión vive en una
  sola corutina).
- `DiskStorage.guardar` es atómico por archivo (tmp+rename con pid en el
  nombre); `Ownership._guardar` lo es también (tmp con pid+uuid).
- `path_seguro` es la frontera contra paths peligrosos (`../`, `\\0`,
  invisibles Unicode, etc.) — se aplica al RECIBIR el mensaje, no solo
  al escribir, para que un path malicioso jamás entre al estado en
  memoria ni se difunda como archivo fantasma.
"""

from .document import Document
from .locks import lineas_tocadas
from .ownership import Ownership
from .paths import path_seguro
from .presence import Roster
from .proposals import Proposals
from .storage import DiskStorage
from .workspace import Workspace

__all__ = [
    "DiskStorage",
    "Document",
    "Ownership",
    "Proposals",
    "Roster",
    "Workspace",
    "lineas_tocadas",
    "path_seguro",
]
