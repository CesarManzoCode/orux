"""Re-export del adapter movido a `orux.adapters.outbound.git.binary`."""

from ..adapters.outbound.git import binary as _real

for _nombre in dir(_real):
    if not _nombre.startswith("__"):
        globals()[_nombre] = getattr(_real, _nombre)
del _nombre, _real
