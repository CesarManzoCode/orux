"""Re-export del submódulo movido a `orux.domain.analysis.lsp`.

Re-exportamos también los símbolos privados (`_X`) porque algunos tests los
inspeccionan directamente.
"""

from ..domain.analysis import lsp as _lsp_real

# Exposición total del namespace (incluidos privados que los tests usan).
for _nombre in dir(_lsp_real):
    if not _nombre.startswith("__"):
        globals()[_nombre] = getattr(_lsp_real, _nombre)
del _nombre, _lsp_real
