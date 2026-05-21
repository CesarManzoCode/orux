"""Tests de la integración con Stripe (capa 30).

Cubren TODA la lógica que se puede probar sin internet: la firma del
webhook (HMAC puro), el armado del cuerpo del Checkout, la traducción
evento -> plan, y la aplicación del evento sobre el store de equipos.

Lo único NO cubierto acá es la llamada de red real a la API de Stripe
(`_crear_sesion_checkout`) y la cáscara HTTP (`api/app.py`): se ejercitan
en el VPS, igual que el OAuth de GitHub o pyright. Por eso `billing.py`
es puro y `aplicar_evento_stripe` solo toca un store inyectable: el
contrato queda fijado al 100% en el sandbox.
"""

from __future__ import annotations

import hmac
import json
from hashlib import sha256

import pytest

from orux import billing
from orux.api.service import aplicar_evento_stripe
from orux.teams import MemTeamStore


def _cabecera_firma(payload: bytes, secret: str, ts: int) -> str:
    """Construye una cabecera `Stripe-Signature` válida, igual que la
    haría Stripe: `t=<ts>,v1=HMAC-SHA256(secret, "<ts>.<payload>")`."""
    firmado = f"{ts}".encode("utf-8") + b"." + payload
    v1 = hmac.new(secret.encode("utf-8"), firmado, sha256).hexdigest()
    return f"t={ts},v1={v1}"


# --- Firma del webhook ---------------------------------------------------


def test_verificar_firma_ok() -> None:
    payload = b'{"type":"checkout.session.completed"}'
    secret = "whsec_test"
    cab = _cabecera_firma(payload, secret, 1_700_000_000)
    assert billing.verificar_firma_webhook(
        payload, cab, secret, ahora=1_700_000_010
    ) is True


def test_verificar_firma_rechaza_payload_alterado() -> None:
    secret = "whsec_test"
    cab = _cabecera_firma(b'{"monto":1}', secret, 1_700_000_000)
    # Mismo encabezado, cuerpo distinto: la firma ya no cuadra. Esto es lo
    # que frena a un atacante que intercepta y modifica el webhook.
    assert billing.verificar_firma_webhook(
        b'{"monto":999}', cab, secret, ahora=1_700_000_010
    ) is False


def test_verificar_firma_rechaza_secreto_incorrecto() -> None:
    payload = b'{"x":1}'
    cab = _cabecera_firma(payload, "whsec_bueno", 1_700_000_000)
    assert billing.verificar_firma_webhook(
        payload, cab, "whsec_malo", ahora=1_700_000_010
    ) is False


def test_verificar_firma_rechaza_timestamp_viejo() -> None:
    # Anti-replay: un webhook firmado hace horas no se puede reusar.
    payload = b'{"x":1}'
    secret = "whsec_test"
    cab = _cabecera_firma(payload, secret, 1_700_000_000)
    assert billing.verificar_firma_webhook(
        payload, cab, secret, ahora=1_700_000_000 + 10_000
    ) is False


def test_verificar_firma_rechaza_cabeceras_basura() -> None:
    payload = b'{"x":1}'
    secret = "whsec_test"
    for cab in ["", "basura", "t=123", "v1=abc", "t=noesnumero,v1=abc"]:
        assert billing.verificar_firma_webhook(payload, cab, secret) is False
    # Secreto vacío: cerrado, nunca pasa.
    cab_ok = _cabecera_firma(payload, "s", 1_700_000_000)
    assert billing.verificar_firma_webhook(
        payload, cab_ok, "", ahora=1_700_000_001
    ) is False


def test_verificar_firma_acepta_una_de_varias_v1() -> None:
    # Durante una rotación del signing secret, Stripe manda varias `v1`;
    # basta que UNA valide.
    payload = b'{"x":1}'
    secret = "whsec_test"
    ts = 1_700_000_000
    v1_buena = _cabecera_firma(payload, secret, ts).split("v1=")[1]
    cab = f"t={ts},v1=deadbeef,v1={v1_buena}"
    assert billing.verificar_firma_webhook(
        payload, cab, secret, ahora=ts + 5
    ) is True


# --- Cuerpo del Checkout -------------------------------------------------


def test_params_checkout_es_suscripcion_con_precio_inline() -> None:
    p = billing.params_checkout(
        "t_abc",
        "Orux Premium · Equipo X",
        "https://orux.space/app/?stripe=success",
        "https://orux.space/app/?stripe=cancel",
        currency="mxn",
        unit_amount=1000,
        interval="month",
    )
    assert p["mode"] == "subscription"
    assert p["line_items[0][price_data][currency]"] == "mxn"
    assert p["line_items[0][price_data][unit_amount]"] == "1000"
    assert p["line_items[0][price_data][recurring][interval]"] == "month"
    # El team_id viaja por triplicado: el webhook necesita encontrarlo
    # tanto en la sesión como en la suscripción.
    assert p["metadata[team_id]"] == "t_abc"
    assert p["subscription_data[metadata][team_id]"] == "t_abc"
    assert p["client_reference_id"] == "t_abc"
    assert p["success_url"].endswith("stripe=success")
    # urlencode no debe romper con las claves anidadas estilo Stripe.
    import urllib.parse

    enc = urllib.parse.urlencode(p)
    assert "line_items%5B0%5D" in enc


# --- Parseo del evento ---------------------------------------------------


def test_evento_de_payload() -> None:
    assert billing.evento_de_payload(b'{"type":"x"}') == {"type": "x"}
    with pytest.raises(ValueError):
        billing.evento_de_payload(b"[]")          # JSON pero no objeto
    with pytest.raises(ValueError):
        billing.evento_de_payload(b"no es json")  # JSONDecodeError < ValueError


# --- Traducción evento -> (team_id, plan) --------------------------------


def test_cambio_de_plan_alta() -> None:
    ev = {
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"team_id": "t1"}}},
    }
    assert billing.cambio_de_plan(ev) == ("t1", "premium")


def test_cambio_de_plan_alta_por_client_reference_id() -> None:
    # La sesión de Checkout también trae el id en client_reference_id;
    # sirve de respaldo si la metadata viniera vacía.
    ev = {
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": "t2", "metadata": {}}},
    }
    assert billing.cambio_de_plan(ev) == ("t2", "premium")


def test_cambio_de_plan_baja() -> None:
    ev = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"team_id": "t3"}}},
    }
    assert billing.cambio_de_plan(ev) == ("t3", "free")


def test_cambio_de_plan_ignora_evento_irrelevante() -> None:
    ev = {
        "type": "invoice.paid",
        "data": {"object": {"metadata": {"team_id": "t1"}}},
    }
    assert billing.cambio_de_plan(ev) is None


def test_cambio_de_plan_sin_team_id_o_forma_rara() -> None:
    assert billing.cambio_de_plan(
        {"type": "checkout.session.completed", "data": {"object": {}}}
    ) is None
    # Formas degeneradas: None, nunca una excepción.
    assert billing.cambio_de_plan({"type": "checkout.session.completed"}) is None
    assert billing.cambio_de_plan({}) is None


# --- Aplicación sobre el store de equipos --------------------------------


async def test_aplicar_evento_sube_y_baja_el_plan() -> None:
    s = MemTeamStore()
    t = await s.crear_equipo("Equipo X", "ana")
    tid = t["id"]
    assert await s.plan(tid) == "free"

    alta = {
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"team_id": tid}}},
    }
    assert await aplicar_evento_stripe(s, alta) == {
        "team_id": tid, "plan": "premium",
    }
    assert await s.plan(tid) == "premium"

    baja = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"team_id": tid}}},
    }
    assert await aplicar_evento_stripe(s, baja) == {
        "team_id": tid, "plan": "free",
    }
    assert await s.plan(tid) == "free"


async def test_aplicar_evento_equipo_inexistente_se_ignora() -> None:
    s = MemTeamStore()
    ev = {
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"team_id": "no-existe"}}},
    }
    assert await aplicar_evento_stripe(s, ev) is None


async def test_aplicar_evento_irrelevante_no_toca_el_plan() -> None:
    s = MemTeamStore()
    t = await s.crear_equipo("Y", "ana")
    ev = {
        "type": "invoice.paid",
        "data": {"object": {"metadata": {"team_id": t["id"]}}},
    }
    assert await aplicar_evento_stripe(s, ev) is None
    assert await s.plan(t["id"]) == "free"


async def test_aplicar_evento_es_idempotente() -> None:
    # Stripe puede reentregar un webhook: aplicarlo dos veces no rompe.
    s = MemTeamStore()
    t = await s.crear_equipo("Z", "ana")
    ev = {
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"team_id": t["id"]}}},
    }
    await aplicar_evento_stripe(s, ev)
    await aplicar_evento_stripe(s, ev)
    assert await s.plan(t["id"]) == "premium"


async def test_webhook_extremo_a_extremo_firma_verifica_aplica() -> None:
    # Replica lo que hace `_billing_webhook` sin la cáscara HTTP: firma ->
    # verifica -> parsea -> aplica. La cáscara solo traduce esto a
    # request/response y se verifica en el VPS.
    s = MemTeamStore()
    t = await s.crear_equipo("E2E", "ana")
    cuerpo = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"team_id": t["id"]}}},
    }).encode("utf-8")
    secret = "whsec_e2e"
    ts = 1_700_000_000
    cab = _cabecera_firma(cuerpo, secret, ts)

    assert billing.verificar_firma_webhook(cuerpo, cab, secret, ahora=ts + 5)
    evento = billing.evento_de_payload(cuerpo)
    assert await aplicar_evento_stripe(s, evento) == {
        "team_id": t["id"], "plan": "premium",
    }
    assert await s.plan(t["id"]) == "premium"
