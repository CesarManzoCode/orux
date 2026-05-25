"""Test contract de Ports: cada adapter cumple su Port estructuralmente.

Los Ports en `orux.ports.persistencia` son `typing.Protocol` con
`runtime_checkable`: `isinstance(adapter, Port)` valida que el adapter
tiene los métodos del contrato. Es un guard rail estructural — si alguien
en el futuro renombra un método del Port y se olvida del adapter, este
test falla con un mensaje claro en vez de un AttributeError en runtime.

Los stores Postgres requieren un `db` para instanciar; pasamos un objeto
dummy (el contract check de Protocol sólo mira los métodos, no los llama).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orux.adapters.analysis import LspFactoryAdapter, SemanticAnalysisAdapter
from orux.adapters.billing import StripeBillingAdapter
from orux.adapters.identity import GithubOAuthAdapter, HmacSessionTokenAdapter
from orux.adapters.json import JsonOwnershipStore, JsonUserStore
from orux.db.stores import (
    PgOwnershipStore,
    PgProposalsStore,
    PgUserStore,
    PgWebhooksStore,
)
from orux.git import GitRepo
from orux.ports import (
    AnalysisPort,
    BillingPort,
    GitPort,
    LspFactoryPort,
    OAuthPort,
    OwnershipStorePort,
    ProposalsStorePort,
    SessionTokenPort,
    TeamStorePort,
    UserStorePort,
    WebhooksStorePort,
    WorkspaceStoragePort,
)
from orux.state import DiskStorage
from orux.state.proposals import MemProposalsStore
from orux.teams import MemTeamStore
from orux.teams.pg import PgTeamStore


class _DbDummy:
    """Marcador para construir los Pg* sin tocar Postgres. El contract
    check sólo verifica que los métodos existan; el `db` no se llama."""


@pytest.fixture
def db_dummy() -> _DbDummy:
    return _DbDummy()


# --- WorkspaceStoragePort -------------------------------------------------

def test_diskstorage_cumple_workspacestorageport(tmp_path: Path) -> None:
    assert isinstance(DiskStorage(tmp_path), WorkspaceStoragePort)


# --- OwnershipStorePort ---------------------------------------------------

def test_json_ownership_cumple_port(tmp_path: Path) -> None:
    assert isinstance(
        JsonOwnershipStore(tmp_path / "o.json"), OwnershipStorePort,
    )


def test_pg_ownership_cumple_port(db_dummy: _DbDummy) -> None:
    assert isinstance(PgOwnershipStore(db_dummy), OwnershipStorePort)


# --- ProposalsStorePort ---------------------------------------------------

def test_mem_proposals_cumple_port() -> None:
    assert isinstance(MemProposalsStore(), ProposalsStorePort)


def test_pg_proposals_cumple_port(db_dummy: _DbDummy) -> None:
    assert isinstance(PgProposalsStore(db_dummy), ProposalsStorePort)


# --- UserStorePort --------------------------------------------------------

def test_json_user_cumple_port(tmp_path: Path) -> None:
    assert isinstance(JsonUserStore(tmp_path / "u.json"), UserStorePort)


def test_pg_user_cumple_port(db_dummy: _DbDummy) -> None:
    assert isinstance(PgUserStore(db_dummy), UserStorePort)


# --- WebhooksStorePort ----------------------------------------------------

def test_pg_webhooks_cumple_port(db_dummy: _DbDummy) -> None:
    assert isinstance(PgWebhooksStore(db_dummy), WebhooksStorePort)


# --- TeamStorePort --------------------------------------------------------

def test_mem_team_cumple_port() -> None:
    assert isinstance(MemTeamStore(), TeamStorePort)


def test_pg_team_cumple_port(db_dummy: _DbDummy) -> None:
    assert isinstance(PgTeamStore(db_dummy), TeamStorePort)


# --- GitPort --------------------------------------------------------------

def test_git_repo_cumple_port(tmp_path: Path) -> None:
    assert isinstance(GitRepo(tmp_path), GitPort)


# --- SessionTokenPort -----------------------------------------------------

def test_hmac_session_cumple_port() -> None:
    assert isinstance(HmacSessionTokenAdapter("secreto"), SessionTokenPort)


# --- OAuthPort ------------------------------------------------------------

def test_github_oauth_cumple_port() -> None:
    assert isinstance(
        GithubOAuthAdapter(
            client_id="cid",
            redirect_uri="https://orux.space/cb",
            state_secret="s",
        ),
        OAuthPort,
    )


# --- BillingPort ----------------------------------------------------------

def test_stripe_billing_cumple_port() -> None:
    assert isinstance(
        StripeBillingAdapter(
            webhook_signing_secret="whsec_test",
            currency="MXN",
            unit_amount=1000,
            interval="month",
            descripcion_producto="Orux Premium",
        ),
        BillingPort,
    )


# --- AnalysisPort + LspFactoryPort ----------------------------------------

def test_semantic_analysis_cumple_port() -> None:
    assert isinstance(SemanticAnalysisAdapter(), AnalysisPort)


def test_lsp_factory_cumple_port() -> None:
    assert isinstance(LspFactoryAdapter(), LspFactoryPort)
