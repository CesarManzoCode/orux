"""GitHub OAuth — lógica pura. Capa nueva sobre la identidad de la capa 7.

Por qué OAuth y por qué así (decisión del usuario):

- El público de laidea (open source, founders técnicos, equipos 2-50) YA
  tiene GitHub. La identidad de sesión pasa a ser una identidad real y
  verificada, sin contraseñas que guardar ni superficie de fuerza bruta
  (eso lo delega GitHub). Encaja con la tesis "todo vive sobre Git".

- **OAuth NO inventa un mecanismo de sesión nuevo.** Su único trabajo es
  producir un token de sesión HMAC idéntico al de la capa 7
  (`crear_token`). Toda la maquinaria del server WS (`_autenticar` ->
  `SessionMessage` -> lobby -> equipo) queda byte-idéntica. Cero cambios de
  protocolo.

- **Identidad con namespace `gh:<login>`** (decisión del usuario, tras
  descartar "login tal cual"). El registro con contraseña está ABIERTO en
  producción: si la identidad OAuth fuese el login pelado, un atacante
  podría pre-registrar con contraseña el nombre = al handle de GitHub de
  una víctima y, cuando esa víctima entrara por GitHub, caería en la cuenta
  cuya contraseña conoce el atacante (apropiación de cuenta real). El
  prefijo `gh:` hace IMPOSIBLE esa colisión: las identidades OAuth y las de
  contraseña viven en espacios disjuntos. Que el prefijo se vea en la UI es
  cosmético y se pule luego con un display-name; la seguridad no se negocia
  en un instance ya desplegado.

Sin dependencias: `hmac`/`hashlib`/`time`/`urllib.parse` son stdlib (igual
que el resto de `identity/`). La parte que SÍ habla con la red (intercambiar
el `code` por un token y leer el perfil) NO está aquí: vive en la cáscara
HTTP, se inyecta, y se prueba en el VPS — este módulo es 100% puro y
testeable en el sandbox sin internet.
"""

from __future__ import annotations

import hmac
import time
from hashlib import sha256
from urllib.parse import urlencode

from .store import normalizar

# Endpoints de GitHub (los usa la cáscara HTTP; acá como única fuente).
URL_AUTORIZA = "https://github.com/login/oauth/authorize"
URL_TOKEN = "https://github.com/login/oauth/access_token"
URL_PERFIL = "https://api.github.com/user"

# Scope mínimo: identidad + email (decisión del usuario). NO se pide `repo`:
# autocompletar clone/push se evaluará aparte; el consentimiento se mantiene
# inofensivo.
SCOPE = "read:user user:email"

# El prefijo que aísla las identidades OAuth de las de contraseña. Si esto
# cambia, cambia la identidad de TODOS los usuarios de GitHub: no tocar a la
# ligera.
PREFIJO_GH = "gh:"


def url_autorizacion(
    client_id: str, redirect_uri: str, state: str, scope: str = SCOPE
) -> str:
    """URL a la que se manda el navegador para que GitHub pida el permiso.

    Pura (solo arma la query). `state` es el token CSRF firmado (ver
    `firmar_state`): GitHub lo devuelve tal cual en el callback y ahí se
    valida — sin estado en el server.
    """
    q = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
        }
    )
    return f"{URL_AUTORIZA}?{q}"


def identidad_github(perfil: dict) -> str:
    """Identidad laidea a partir del JSON de `GET /user` de GitHub.

    `gh:` + login normalizado (trim+minúsculas, igual que toda la identidad
    de la capa 7, para que el ownership no se parta por mayúsculas). El
    login de GitHub es único y estable; el `id` numérico sería aún más
    estable ante renames, pero rompería la legibilidad en presencia/commits
    y los renames de handle son raros — decisión consciente de prototipo.

    `ValueError` si el perfil no trae un login usable: el llamador lo trata
    como "OAuth falló", nunca como caída.
    """
    login = perfil.get("login")
    if not isinstance(login, str) or not normalizar(login):
        raise ValueError("el perfil de GitHub no trae un login válido")
    return f"{PREFIJO_GH}{normalizar(login)}"


def firmar_state(secret: str, ahora: float | None = None) -> str:
    """Token CSRF *stateless* para el parámetro `state` de OAuth.

    Formato `<emitido_en>.<hmac>`. No se guarda nada en el server: la
    validez se prueba con la firma + la antigüedad. Mismo principio que el
    token de sesión de la capa 7, pero efímero (segundos de vida) y para
    otra cosa: que el callback que llega sea el que ESTE server inició, no
    uno fabricado por un tercero (CSRF/login forzado).
    """
    ts = str(int(ahora if ahora is not None else time.time()))
    return f"{ts}.{_firma_state(ts, secret)}"


def validar_state(
    state: str,
    secret: str,
    max_edad: float = 600.0,
    ahora: float | None = None,
) -> bool:
    """¿`state` lo firmó este server y no está vencido? Comparación en
    tiempo constante. False ante cualquier cosa que no sea un state legítimo
    y fresco (formato roto, firma falsa, vencido): el llamador lo trata como
    "no autenticado", nunca como excepción."""
    try:
        ts_str, firma = state.split(".", 1)
    except (ValueError, AttributeError):
        return False
    if not hmac.compare_digest(firma, _firma_state(ts_str, secret)):
        return False
    try:
        emitido = int(ts_str)
    except ValueError:
        return False
    t = ahora if ahora is not None else time.time()
    # Vencido o con timestamp en el futuro (reloj manipulado): no vale.
    return 0 <= (t - emitido) <= max_edad


def _firma_state(ts: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), ts.encode("ascii"), sha256
    ).hexdigest()
