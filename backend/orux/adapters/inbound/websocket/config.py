"""Topes y perillas de runtime del servidor de sincronización.

Todo lo que el operador puede ajustar por variable de entorno vive acá,
aislado de la lógica del server (`sync.py`) y del estado de equipo
(`runtime.py`). Son límites defensivos: sin ellos un mensaje gigante o un
cliente que spamea pueden saturar a un equipo entero. Cada valor se lee una
vez al importar el módulo y se *clampa* a un rango sano — un env tipo `-1` o
`999999999` no rompe nada.
"""

from __future__ import annotations

import os
import time

# Topes y constantes de runtime ajustables por env (con clamp defensivo).
# Sin esto, un mensaje gigante (BACKEND-AUDIT-0222 / -0272) o un cliente que
# spamea pueden saturar el equipo entero. Los defaults son holgados.
# Los helpers viven en `orux/_env.py` (antes 3 copias en config/pool/workspace);
# se re-exportan acá para que los imports existentes
# (`from .config import _env_int`) sigan funcionando byte-idéntico.
from orux._env import _env_float, _env_int

# Puerto WS por defecto. Constante centralizada (antes hardcodeada en tres
# lugares: `composition.py:AppConfig.port`, el default del env `ORUX_PORT`
# y la firma de `SyncServer.run`); con la constante, cambiar el puerto es
# una sola edición y los tres consumidores convergen.
DEFAULT_WS_PORT = 8765

__all__ = ["_env_int", "_env_float", "DEFAULT_WS_PORT"]


# Tope HARD del frame WS recibido. websockets.serve() lo aplica antes de
# entregar el frame al handler — protege ANTES de `decode` (que también
# valida, defensa en profundidad).
WS_MAX_SIZE = _env_int("ORUX_WS_MAX_SIZE", 2 * 1024 * 1024, 64 * 1024, 16 * 1024 * 1024)
# Cola por conexión: cuántos frames sin leer se aceptan antes de cerrar.
WS_MAX_QUEUE = _env_int("ORUX_WS_MAX_QUEUE", 32, 4, 1024)
# Rate-limit por conexión: token bucket. Sin esto, un cliente puede saturar al
# equipo entero con miles de mensajes/s (BACKEND-AUDIT-0272). 50/s sostenido
# con burst 100 cubre tecleo humano agresivo + ráfagas legítimas (commit,
# admin_assign_many) y mata el spam.
RATE_TASA = _env_float("ORUX_RATE_PER_SEC", 50.0, 1.0, 1000.0)
RATE_BURST = _env_float("ORUX_RATE_BURST", 100.0, 1.0, 10_000.0)


# --- Validación de Origin (anti-CSRF WebSocket) ---------------------------
#
# El navegador envía el header `Origin` en el handshake WS. Si no validamos,
# un sitio malicioso puede forzar el navegador de un usuario autenticado a
# conectarse al server y ejecutar acciones en su nombre. websockets.serve()
# tiene soporte nativo: pasamos `origins=[...]` y rechaza handshakes cuyo
# Origin no esté en la lista (HTTP 403 antes de despachar al handler).
#
# IMPORTANTE — whitelist:
# - Cada cliente NUEVO con browser tiene que sumarse explícitamente a la
#   whitelist (`ORUX_WS_ORIGINS`). El olvido = los usuarios de ese cliente
#   no pueden conectarse.
# - Clientes NO-browser (tests Python, Electron, plugins de IDE futuros,
#   `wscat`, healthchecks) NO mandan Origin: incluimos `None` en la lista
#   para que pasen. Esto es seguro porque CSRF requiere un browser que
#   monte el Origin automáticamente.
#
# Formatos del env:
# - vacío o default: solo `https://orux.space` + clientes sin Origin
#   (cubre prod y el healthcheck del Docker; localhost dev se añade manual o
#   se infiere automáticamente cuando `ORUX_DB_DSN` está vacío — modo dev sin
#   Postgres)
# - CSV ("https://orux.space,http://localhost:5173"): esos + sin Origin
# - "*": aceptar TODO (incluye clientes browser arbitrarios; usar SOLO en
#   debug puntual, jamás en prod)
#
# AUDITORIA-SEGURIDAD 2026-05-25 A-WS-02: el default NO incluye localhost en
# producción. Si un operador olvidaba setear `ORUX_WS_ORIGINS` en el VPS, un
# atacante podía forzar a un proxy local a servir HTML en localhost:5173 y
# montar CSRF contra el WS con el `orux_session` de la víctima. Para no
# romper el dev local (Vite en :5173), el código de abajo añade localhost al
# default cuando detecta modo dev (sin `ORUX_DB_DSN` => no hay Postgres =>
# no es producción).
_DEF_ORIGINS_PROD = "https://orux.space"
_DEF_ORIGINS_DEV_EXTRAS = "http://localhost:5173,http://localhost:8080"


def _default_origins() -> str:
    # Modo dev: sin Postgres, abrimos localhost también para que el cliente
    # Vite y el static server local conecten sin tener que setear nada.
    # Modo prod (con ORUX_DB_DSN): solo el dominio público; el operador debe
    # setear ORUX_WS_ORIGINS explícitamente si necesita otros orígenes.
    if not os.environ.get("ORUX_DB_DSN", "").strip():
        return f"{_DEF_ORIGINS_PROD},{_DEF_ORIGINS_DEV_EXTRAS}"
    return _DEF_ORIGINS_PROD


def _parse_origins(env: str) -> list[str | None] | None:
    crudo = (env or "").strip()
    if crudo == "*":
        return None  # websockets: sin filtro (modo permisivo)
    items = [o.strip() for o in crudo.split(",") if o.strip()]
    # `None` permite handshakes sin Origin (clientes no-browser).
    return [*items, None] if items else [None]


WS_ORIGINS = _parse_origins(
    os.environ.get("ORUX_WS_ORIGINS", _default_origins())
)


class _RateLimiter:
    """Token bucket simple por conexión. No usa lock: cada conexión vive en
    una sola corutina, así que el acceso es serial. `permitir()` devuelve
    True si hay token; False si hay que tirar el mensaje."""

    __slots__ = ("_tokens", "_tasa", "_burst", "_t")

    def __init__(self, tasa: float, burst: float) -> None:
        self._tokens = float(burst)
        self._tasa = float(tasa)
        self._burst = float(burst)
        self._t = time.monotonic()

    def permitir(self) -> bool:
        ahora = time.monotonic()
        elapsed = ahora - self._t
        self._t = ahora
        self._tokens = min(self._burst, self._tokens + elapsed * self._tasa)
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
