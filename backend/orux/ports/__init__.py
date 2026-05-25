"""Ports: contratos formales que el dominio exige a la infraestructura.

Hexagonal: el dominio (`state/`, `analysis/`, `identity/` puro) declara QUÉ
necesita persistir; cada Port es un `typing.Protocol` y la implementación
concreta (en `adapters/`, `db/`, `teams/`) cumple ese contrato sin importar
nada del dominio.

Re-export plano para callers internos: `from orux.ports import OwnershipStorePort`.
"""

from .analysis import AnalysisPort, LspFactoryPort, LspSession
from .billing import BillingPort
from .git import EstadoGit, GitPort
from .identity import OAuthPort, SessionTokenPort
from .persistencia import (
    OwnershipStorePort,
    ProposalsStorePort,
    TeamStorePort,
    UserStorePort,
    WebhooksStorePort,
    WorkspaceStoragePort,
)

__all__ = [
    "AnalysisPort",
    "BillingPort",
    "EstadoGit",
    "GitPort",
    "LspFactoryPort",
    "LspSession",
    "OAuthPort",
    "OwnershipStorePort",
    "ProposalsStorePort",
    "SessionTokenPort",
    "TeamStorePort",
    "UserStorePort",
    "WebhooksStorePort",
    "WorkspaceStoragePort",
]
