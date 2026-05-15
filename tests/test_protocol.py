"""Tests del protocolo de mensajes.

Estos tests son las pruebas más rápidas que tenemos: no abren sockets, no esperan
nada, solo verifican que `encode` y `decode` son inversos uno del otro. Si esto
se rompe, todo lo demás se cae detrás, así que los tests de integración asumen
que estos pasan.
"""

import pytest

from laidea.protocol import InitMessage, UpdateMessage, decode, encode


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
