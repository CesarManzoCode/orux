"""Re-export del submódulo movido a `orux.domain.analysis.rust`."""

from ..domain.analysis import rust as _real

for _nombre in dir(_real):
    if not _nombre.startswith("__"):
        globals()[_nombre] = getattr(_real, _nombre)
del _nombre, _real
