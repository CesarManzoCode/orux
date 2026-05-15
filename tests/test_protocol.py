"""Tests del protocolo de mensajes.

Estos tests son las pruebas más rápidas que tenemos: no abren sockets, no esperan
nada, solo verifican que `encode` y `decode` son inversos uno del otro. Si esto
se rompe, todo lo demás se cae detrás, así que los tests de integración asumen
que estos pasan.
"""

import pytest

from laidea.protocol import (
    InitMessage,
    LeaveMessage,
    PresenceMessage,
    PresenceState,
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
