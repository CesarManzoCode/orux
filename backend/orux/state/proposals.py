"""Re-export del submódulo movido a `orux.domain.state.proposals`."""

from ..domain.state.proposals import *  # noqa: F401,F403
from ..domain.state.proposals import (  # noqa: F401
    MAX_CONTENT_BYTES,
    MAX_POR_AUTOR,
    MemProposalsStore,
    Proposals,
    PropuestaInvalida,
)
