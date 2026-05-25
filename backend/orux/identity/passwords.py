"""Re-export del submódulo movido a `orux.domain.identity.passwords`."""

from ..domain.identity.passwords import *  # noqa: F401,F403
from ..domain.identity.passwords import (  # noqa: F401
    MARCADOR_EXTERNO,
    hash_password,
    verificar_password,
)
