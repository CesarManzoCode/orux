"""Tests del protocolo de mensajes.

Estos tests son las pruebas más rápidas que tenemos: no abren sockets, no esperan
nada, solo verifican que `encode` y `decode` son inversos uno del otro. Si esto
se rompe, todo lo demás se cae detrás, así que los tests de integración asumen
que estos pasan.
"""

import pytest

from laidea.protocol import (
    AuthErrorMessage,
    AuthOkMessage,
    ClaimMessage,
    GitRefreshMessage,
    GitStatusMessage,
    ImpactMessage,
    LoginMessage,
    RegisterMessage,
    SessionMessage,
    InitMessage,
    LeaveMessage,
    OwnershipMessage,
    PresenceMessage,
    PresenceState,
    Proposal,
    ProposalMessage,
    ResolveMessage,
    UpdateMessage,
    WelcomeMessage,
    decode,
    encode,
)


def test_encode_decode_init_roundtrip() -> None:
    msg = InitMessage(files={"main.py": "print('hi')", "notas.md": "# título"})
    assert decode(encode(msg)) == msg


def test_init_with_no_files_is_valid() -> None:
    # Workspace recién arrancado, sin archivos todavía. El cliente debe poder
    # manejar este caso (textarea deshabilitado hasta que cree el primer archivo).
    msg = InitMessage()
    assert decode(encode(msg)) == InitMessage(files={})


def test_encode_decode_update_roundtrip() -> None:
    msg = UpdateMessage(path="src/auth.py", content="def login(): pass")
    assert decode(encode(msg)) == msg


def test_decode_rejects_unknown_type() -> None:
    # Si alguien manda un tipo desconocido, gritamos fuerte. Mejor que adivinar.
    with pytest.raises(ValueError):
        decode('{"type": "nope"}')


# --- Capa 2: mensajes de presencia ---


def test_encode_decode_welcome_roundtrip() -> None:
    # Welcome lleva tu identidad + el roster de los demás (PresenceState
    # anidados). El roundtrip valida que asdict baja recursivamente y que
    # decode reconstruye los PresenceState anidados.
    msg = WelcomeMessage(
        you=PresenceState(client_id="3", name="anónimo-3", color="#5fa8e0"),
        peers=[
            PresenceState(
                client_id="1", name="anónimo-1", color="#e0607a",
                path="auth.py", line=12,
            )
        ],
    )
    assert decode(encode(msg)) == msg


def test_encode_decode_presence_roundtrip() -> None:
    msg = PresenceMessage(
        client_id="2", name="anónimo-2", color="#8de0a8", path="main.py", line=7
    )
    assert decode(encode(msg)) == msg


def test_decode_presence_from_client_without_identity() -> None:
    # El cliente solo manda path+line; el servidor rellena la identidad. decode
    # no debe explotar por la falta de client_id/name/color.
    msg = decode('{"type": "presence", "path": "x.py", "line": 4}')
    assert isinstance(msg, PresenceMessage)
    assert (msg.path, msg.line) == ("x.py", 4)
    assert msg.client_id == "" and msg.name == "" and msg.color == ""


def test_encode_decode_leave_roundtrip() -> None:
    msg = LeaveMessage(client_id="5")
    assert decode(encode(msg)) == msg


# --- Capa 4: ownership + edición tentativa ---


def test_encode_decode_claim_roundtrip() -> None:
    msg = ClaimMessage(path="src/auth.py")
    assert decode(encode(msg)) == msg


def test_encode_decode_ownership_roundtrip() -> None:
    msg = OwnershipMessage(owners={"main.py": "1", "auth.py": "3"})
    assert decode(encode(msg)) == msg


def test_ownership_vacio_es_valido() -> None:
    assert decode(encode(OwnershipMessage())) == OwnershipMessage(owners={})


def test_encode_decode_proposal_roundtrip() -> None:
    # Proposal va anidado dentro de ProposalMessage (como PresenceState en
    # WelcomeMessage): el roundtrip valida que asdict baja recursivo y decode
    # reconstruye el anidado.
    msg = ProposalMessage(
        proposal=Proposal(
            id="main.py::2",
            path="main.py",
            author_id="2",
            author_name="anónimo-2",
            content="print('hola')",
        )
    )
    assert decode(encode(msg)) == msg


def test_encode_decode_resolve_roundtrip() -> None:
    assert decode(encode(ResolveMessage("main.py::2", True))) == ResolveMessage(
        "main.py::2", True
    )
    assert decode(encode(ResolveMessage("main.py::2", False))) == ResolveMessage(
        "main.py::2", False
    )


# --- Capa 6: análisis de impacto ---


def test_encode_decode_impact_roundtrip() -> None:
    msg = ImpactMessage(
        source_path="models.py",
        author_name="anónimo-2",
        affected_path="auth.py",
        symbols=["Usuario", "rol_de"],
    )
    assert decode(encode(msg)) == msg


# --- Capa 7: identidad real ---


def test_encode_decode_auth_messages_roundtrip() -> None:
    for msg in (
        RegisterMessage(username="ana", password="x"),
        LoginMessage(username="ana", password="x"),
        SessionMessage(token="abc.def"),
        AuthOkMessage(username="ana", token="abc.def"),
        AuthErrorMessage(reason="usuario o contraseña incorrectos"),
    ):
        assert decode(encode(msg)) == msg


def test_encode_decode_git_messages_roundtrip() -> None:
    for msg in (
        GitStatusMessage(available=True, branch="main", changes=3,
                          commits=["a1b2 primer commit", "c3d4 segundo"]),
        GitStatusMessage(available=False),
        GitRefreshMessage(),
    ):
        assert decode(encode(msg)) == msg
