"""Re-export del submódulo movido a `orux.domain.analysis.modelo`."""

from ..domain.analysis import modelo as _real

for _nombre in dir(_real):
    if not _nombre.startswith("__"):
        globals()[_nombre] = getattr(_real, _nombre)
del _nombre, _real
