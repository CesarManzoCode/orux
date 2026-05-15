"""Tests del protocolo de mensajes."""

import pytest

from laidea.protocol import InitMessage, UpdateMessage, decode, encode


def test_encode_decode_init_roundtrip() -> None:
    msg = InitMessage(content="hola")
    assert decode(encode(msg)) == msg


def test_encode_decode_update_roundtrip() -> None:
    msg = UpdateMessage(content="mundo")
    assert decode(encode(msg)) == msg


def test_decode_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        decode('{"type": "nope", "content": ""}')
