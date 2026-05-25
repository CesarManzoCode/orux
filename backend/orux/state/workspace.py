"""Re-export del submódulo movido a `orux.domain.state.workspace`."""

from ..domain.state.workspace import *  # noqa: F401,F403
from ..domain.state.workspace import (  # noqa: F401
    MAX_ARCHIVOS,
    MAX_BYTES_ARCHIVO,
    MAX_BYTES_TOTAL,
    Workspace,
    WorkspaceLleno,
    _env_int,  # test_robustez_extras verifica que es el mismo símbolo
)
