"""Re-export del módulo movido a `orux.adapters.inbound.http.app`."""

from ..adapters.inbound.http import app as _real

for _nombre in dir(_real):
    if not _nombre.startswith("__"):
        globals()[_nombre] = getattr(_real, _nombre)
del _nombre, _real
