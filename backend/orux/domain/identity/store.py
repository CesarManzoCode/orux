"""Registro de usuarios en memoria. Memoria pura.

Es el modelo del dominio "quién existe". Capa 7 lo introdujo como mínimo
self-hosted con persistencia inline a JSON; el refactor hex sacó esa
persistencia a `adapters.json.JsonUserStore` (que cumple `UserStorePort`),
dejando esta clase como memoria sync pura: testeable sin disco, hidratable
desde cualquier store externo (`inicial=await store.cargar(...)`).

Decisiones de prototipo, preservadas:

- **Estructura interna**: `usuario_normalizado -> registro`. El registro
  puede ser un string (legacy: solo el hash de pwd) o un dict
  `{"hash": "...", "epoch": N}` con epoch de sesiones.
- **El usuario se normaliza** (trim + casefold + NFKC): "Joaquin",
  "joaquin", "JOAQUIN" o "ﬁoaquin" (con ligadura U+FB01) son el mismo, para
  que el ownership no se parta por mayúsculas o por homoglifos unicode.
- La contraseña nunca se guarda en claro; se delega de inmediato en
  `passwords` (PBKDF2 + sal).

Persistencia (cuando aplica): el caller mantiene un adapter externo
(`JsonUserStore` en dev / tests, `PgUserStore` en producción) y orquesta
hidratar al construir / escribir-a-través tras cada mutación.
"""

from __future__ import annotations

import threading
import unicodedata

from .passwords import MARCADOR_EXTERNO, hash_password, verificar_password


def normalizar(username: str) -> str:
    """Forma canónica del usuario. Misma entrada -> mismo dueño siempre.

    AUDITORIA-SEGURIDAD 2026-05-25 A-AUTH-02:
    - `casefold()` en vez de `lower()`: cubre formas como ß (alemán) que
      lower() deja igual pero casefold convierte a 'ss'. Sin esto, dos
      usuarios "groß" y "gross" podrían coexistir.
    - NFKC normaliza homoglifos (ligaturas como ﬁ→fi, espacios
      especiales, dígitos en círculo, etc.). Un atacante podría
      registrarse como `joaquın` (i sin punto, U+0131) para asemejarse a
      `joaquin` y confundir a víctimas. NFKC los unifica."""
    if not isinstance(username, str):
        return ""
    # NFKC primero: descompone homoglifos antes del casefold.
    return unicodedata.normalize("NFKC", username).strip().casefold()


# Reglas del usuario nuevo (sólo se aplican al CREAR cuenta; las cuentas
# viejas siguen existiendo aunque no cumplan — no rompemos a nadie). Charset
# ASCII estricto y prefijo reservado para OAuth: `gh:` es para identidades
# que vienen de GitHub (capa OAuth), no se puede registrar uno a mano con
# ese prefijo o un atacante secuestra al usuario `foo` registrándose como
# `gh:foo` antes de que entre por GitHub.
#
# Charset reducido (BACKEND-AUDIT-0008): se quitaron `+` y `@` para evitar
# (a) lookalikes con emails (`paypal+verify`), (b) que `user@host` se
# interprete como user-en-host si en un futuro el username viaja en URL.
_USUARIO_MIN = 2
_USUARIO_MAX = 32
_USUARIO_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
# Prefijo reservado: el `gh:` puede llegar a tener hasta 39 chars (límite de
# GitHub) + 3 del prefijo = 42 chars. El usuario interno excede `_USUARIO_MAX`
# a propósito (su namespace lo gobierna OAuth, no `registrar`). El cap real
# de `asegurar_externo` es el real para gh:.
_USUARIO_GH_MAX = 39 + len("gh:")
_USUARIO_PREFIJOS_RESERVADOS = ("gh:",)


def validar_nuevo_usuario(username: str) -> str:
    """Normaliza y valida un usuario PARA REGISTRO (no para login). Devuelve
    la forma canónica. Lanza `ValueError` con mensaje legible si no pasa.

    Sólo se aplica en `registrar`: las sesiones de usuarios viejos siguen
    funcionando aunque su nombre tenga caracteres que ya no aceptaríamos
    (migración sin romper a nadie).
    """
    if not isinstance(username, str):
        raise ValueError("usuario inválido")
    u = normalizar(username)
    if not u:
        raise ValueError("usuario inválido")
    if len(u) < _USUARIO_MIN:
        raise ValueError(f"el usuario es muy corto (mínimo {_USUARIO_MIN})")
    if len(u) > _USUARIO_MAX:
        raise ValueError(f"el usuario es muy largo (máximo {_USUARIO_MAX})")
    if u[0] in ".-_":
        raise ValueError("el usuario debe empezar con letra o número")
    for c in u:
        if c not in _USUARIO_CHARS:
            raise ValueError("usa solo letras, números, '.', '_' o '-'")
    for pre in _USUARIO_PREFIJOS_RESERVADOS:
        if u.startswith(pre):
            raise ValueError(
                f"el prefijo '{pre}' está reservado — elige otro nombre"
            )
    return u


def _hash_de_registro(registro: object) -> str | None:
    """Extrae el hash de un registro (string legacy o dict nuevo). None si
    el registro es estructuralmente inválido (BACKEND-AUDIT-0025)."""
    if isinstance(registro, str):
        return registro
    if isinstance(registro, dict):
        h = registro.get("hash")
        return h if isinstance(h, str) else None
    return None


def _epoch_de_registro(registro: object) -> int:
    """Epoch de sesiones del registro. 0 para registros legacy (sin dict).
    Los tokens emitidos antes del fix llevan epoch=0 implícito y siguen
    valiendo hasta que el usuario revoque (cambio de pwd lo hace)."""
    if isinstance(registro, dict):
        e = registro.get("epoch", 0)
        if isinstance(e, int) and not isinstance(e, bool):
            return e
    return 0


class UserStore:
    """Memoria pura. Sync. La persistencia (cuando aplica) la gestiona el
    caller vía `UserStorePort` (`JsonUserStore` / `PgUserStore`).

    `inicial`: snapshot opcional desde un store externo. El caller hace
    algo como `users = UserStore(inicial=await store.cargar_todo())`. Para
    tests sin persistencia (la gran mayoría) basta con `UserStore()`.
    """

    def __init__(
        self,
        inicial: dict[str, object] | None = None,
    ) -> None:
        # usuario_normalizado -> registro (string legacy o dict nuevo).
        self._usuarios: dict[str, object] = dict(inicial) if inicial else {}
        # Lock para `registrar`/`asegurar_externo` (BACKEND-AUDIT-0026 TOCTOU).
        # threading.Lock porque los métodos son sync; el lock cubre check + set.
        self._lock = threading.Lock()

    def existe(self, username: str) -> bool:
        return normalizar(username) in self._usuarios

    def registrar(self, username: str, password: str) -> str:
        """Crea un usuario. Devuelve su forma canónica.

        Levanta `ValueError` si el usuario está vacío, viola las reglas de
        formato (charset/longitud/prefijo reservado) o ya existe.
        """
        u = validar_nuevo_usuario(username)
        with self._lock:
            if u in self._usuarios:
                raise ValueError("ese usuario ya existe")
            self._usuarios[u] = {
                "hash": hash_password(password),
                "epoch": 0,
            }
        return u

    def asegurar_externo(self, username: str) -> str:
        """Garantiza una cuenta para una identidad externa (OAuth GitHub),
        SIN contraseña. Idempotente. Devuelve la forma canónica.

        `SessionMessage` (capa 7) exige que el usuario exista en el store; un
        usuario que entra por GitHub no pasó por `registrar`. Esto lo crea la
        primera vez con `MARCADOR_EXTERNO` (que `verificar_password` rechaza
        siempre): existe para `existe()`, pero NO se puede entrar por
        contraseña. La identidad ya viene con namespace `gh:` desde
        `identidad_github`, así que jamás colisiona con una cuenta de
        contraseña.
        """
        u = normalizar(username)
        if not u:
            raise ValueError("usuario inválido")
        if len(u) > _USUARIO_GH_MAX:
            raise ValueError("usuario externo demasiado largo")
        cuerpo = u[len("gh:"):] if u.startswith("gh:") else u
        for c in cuerpo:
            if c not in _USUARIO_CHARS:
                raise ValueError(
                    "usuario externo con caracteres no permitidos"
                )
        with self._lock:
            if u not in self._usuarios:
                self._usuarios[u] = {"hash": MARCADOR_EXTERNO, "epoch": 0}
        return u

    def admin(self) -> str | None:
        """El admin del workspace = el PRIMER usuario registrado.

        Capa 12 (pre-multi-team). Hoy producción usa el rol DENTRO del
        equipo (capa 15); `admin()` queda como utilidad legacy del modelo
        single-team. `dict` preserva orden de inserción en Python 3.7+,
        así que el primer key es quien se registró primero.
        """
        return next(iter(self._usuarios), None)

    def usuarios(self) -> list[str]:
        """Todos los usuarios registrados (orden estable)."""
        return sorted(self._usuarios)

    def epoch(self, username: str) -> int:
        """Contador de sesiones del usuario. Los tokens llevan su valor al
        emitirse; revocar = incrementar (cambio de pwd, logout-all)."""
        return _epoch_de_registro(self._usuarios.get(normalizar(username)))

    def revocar_sesiones(self, username: str) -> None:
        """Invalida TODOS los tokens vivos de `username` (BACKEND-AUDIT-0002)."""
        u = normalizar(username)
        with self._lock:
            reg = self._usuarios.get(u)
            if reg is None:
                return
            h = _hash_de_registro(reg) or MARCADOR_EXTERNO
            self._usuarios[u] = {
                "hash": h, "epoch": _epoch_de_registro(reg) + 1,
            }

    def cambiar_password(self, username: str, password: str) -> bool:
        """Reemplaza la contraseña del usuario y revoca sus sesiones vivas.
        True si el usuario existía, False si no. Legacy: no se cablea en
        producción hoy (no hay flujo de cambio de contraseña en el UI),
        se mantiene como API documentada por si entra ese flujo."""
        u = normalizar(username)
        with self._lock:
            if u not in self._usuarios:
                return False
            reg = self._usuarios[u]
            self._usuarios[u] = {
                "hash": hash_password(password),
                "epoch": _epoch_de_registro(reg) + 1,
            }
        return True

    def verificar(self, username: str, password: str) -> bool:
        """¿Usuario existe y la contraseña coincide? False si cualquiera falla."""
        registro = self._usuarios.get(normalizar(username))
        h = _hash_de_registro(registro)
        if h is None:
            return False
        return verificar_password(password, h)
