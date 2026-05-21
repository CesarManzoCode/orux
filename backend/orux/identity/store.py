"""Registro de usuarios persistido. Núcleo de la capa 7.

Es a la identidad lo que `DiskStorage` es al workspace: el estado autoritativo
de "quién existe", guardado en disco para que sobreviva a reiniciar el server.
Mismo patrón de inyección de dependencias: recibe la ruta del archivo; el
server real la cablea, los tests usan `tmp_path`.

Decisiones de prototipo, documentadas porque no son obvias:

- **Un solo archivo JSON** `usuario -> registro`. Suficiente para 2-50
  personas (el público objetivo). Nada de base de datos todavía.
  El registro puede ser un string (legacy: solo el hash de pwd) o un dict
  `{"hash": "...", "epoch": N}` con epoch de sesiones (fix BACKEND-AUDIT-0002).
- **El usuario se normaliza** (trim + minúsculas): "Joaquin" y "joaquin" son
  el mismo, para que el ownership no se parta por mayúsculas.
- La contraseña nunca se guarda ni pasa por aquí en claro más de lo
  imprescindible: se delega de inmediato en `passwords` (PBKDF2 + sal).
- **Permisos restrictivos** (0o600) al persistir: el JSON tiene hashes
  PBKDF2, no se expone a otros usuarios del host (fix BACKEND-AUDIT-0013).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .passwords import MARCADOR_EXTERNO, hash_password, verificar_password


def normalizar(username: str) -> str:
    """Forma canónica del usuario. Misma entrada -> mismo dueño siempre."""
    return username.strip().lower()


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
    def __init__(self, path: Path | str | None = None) -> None:
        # None = en memoria (tests), igual que DiskStorage/Ownership. Con ruta,
        # los usuarios sobreviven a reiniciar el server.
        self._path = Path(path) if path is not None else None
        # usuario_normalizado -> registro (string legacy o dict nuevo).
        self._usuarios: dict[str, object] = {}
        # Lock para `registrar`/`asegurar_externo` (BACKEND-AUDIT-0026 TOCTOU).
        # threading.Lock porque las llamadas vienen indirectamente desde
        # corutinas via `to_thread` o de adapters async; cubrir el camino del
        # check + asignación es suficiente y trivial.
        self._lock = threading.Lock()
        if self._path is not None and self._path.exists():
            try:
                cargado = json.loads(self._path.read_text(encoding="utf-8"))
                if not isinstance(cargado, dict):
                    raise ValueError("estructura inesperada en users.json")
                # Validación estructural (BACKEND-AUDIT-0025): ignoramos
                # entradas mal formadas en vez de explotar.
                limpio: dict[str, object] = {}
                for k, v in cargado.items():
                    if not isinstance(k, str):
                        continue
                    if isinstance(v, str) or (
                        isinstance(v, dict) and isinstance(v.get("hash"), str)
                    ):
                        limpio[k] = v
                self._usuarios = limpio
            except (ValueError, OSError):
                # Archivo corrupto: arrancamos vacío en vez de tumbar el server.
                # En un prototipo es preferible "nadie registrado" a no arrancar.
                self._usuarios = {}

    def _guardar(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atómico (robustez B-varios): temporal + os.replace.
        # Tmp con pid para evitar colisión cross-proceso (BACKEND-AUDIT-0011).
        # Sigue sin ser bulletproof multi-writer (eso quiere Postgres) pero
        # dos procesos compitiendo ya no se pisan el tmp.
        tmp = self._path.with_suffix(f"{self._path.suffix}.{os.getpid()}.tmp")
        # Permisos restrictivos al crear (BACKEND-AUDIT-0013). os.open con
        # 0o600 → otros usuarios del host no leen el JSON con hashes PBKDF2.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._usuarios, f)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        os.replace(tmp, self._path)
        # Por si el archivo ya existía con permisos laxos: forzamos 0600.
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    def existe(self, username: str) -> bool:
        return normalizar(username) in self._usuarios

    def registrar(self, username: str, password: str) -> str:
        """Crea un usuario. Devuelve su forma canónica. Persiste.

        Levanta `ValueError` si el usuario está vacío, viola las reglas de
        formato (charset/longitud/prefijo reservado) o ya existe: el llamador
        (server) traduce eso a un error de registro para el cliente, no a una
        caída.
        """
        # `validar_nuevo_usuario` aplica las reglas DURAS al registrar (sólo
        # ASCII alfanumérico + `._-`, 2-32 chars, prefijos OAuth reservados).
        # Cuentas antiguas siguen funcionando vía `verificar` / `existe` con
        # `normalizar` plano — esto solo gatea la creación de NUEVAS cuentas.
        u = validar_nuevo_usuario(username)
        # Lock cubre el check + assignación (TOCTOU BACKEND-AUDIT-0026).
        with self._lock:
            if u in self._usuarios:
                raise ValueError("ese usuario ya existe")
            self._usuarios[u] = {
                "hash": hash_password(password),  # valida password vacía/larga
                "epoch": 0,
            }
            self._guardar()
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

        Valida longitud/charset (incluyendo prefijo gh:) para defender contra
        un identifier externo manipulado (BACKEND-AUDIT-0009)."""
        u = normalizar(username)
        if not u:
            raise ValueError("usuario inválido")
        if len(u) > _USUARIO_GH_MAX:
            raise ValueError("usuario externo demasiado largo")
        # Charset estricto para gh:<login>: el resto debe pasar el ASCII
        # general (no espacios, no chars de control). GitHub permite [a-z0-9]
        # y guiones; nuestro `_USUARIO_CHARS` es superset razonable.
        cuerpo = u[len("gh:"):] if u.startswith("gh:") else u
        for c in cuerpo:
            if c not in _USUARIO_CHARS:
                raise ValueError("usuario externo con caracteres no permitidos")
        with self._lock:
            if u not in self._usuarios:
                self._usuarios[u] = {"hash": MARCADOR_EXTERNO, "epoch": 0}
                self._guardar()
        return u

    def admin(self) -> str | None:
        """El admin del workspace = el PRIMER usuario registrado.

        Capa 12. Decisión deliberadamente mínima y sin migración: no se añade
        ningún campo al JSON. `dict` (y `json`) preservan orden de inserción
        en Python 3.7+, así que el primer key es, por construcción, quien se
        registró primero — la persona que levantó el instance. En tu VPS es
        tu propia cuenta, retroactivamente, sin tocar `users.json`.

        None si no hay nadie registrado todavía. Promover/cambiar de admin
        sería otra pieza chica (y otra capa): acá el admin es uno y fijo.
        """
        return next(iter(self._usuarios), None)

    def usuarios(self) -> list[str]:
        """Todos los usuarios registrados (orden estable para la UI del panel
        admin). Es solo la lista de nombres; nunca sale de aquí un registro de
        contraseña."""
        return sorted(self._usuarios)

    def epoch(self, username: str) -> int:
        """Contador de sesiones del usuario. Los tokens llevan su valor al
        emitirse; revocar = incrementar (cambio de pwd, logout-all)."""
        return _epoch_de_registro(self._usuarios.get(normalizar(username)))

    def revocar_sesiones(self, username: str) -> None:
        """Invalida TODOS los tokens vivos de `username` (BACKEND-AUDIT-0002).
        Incrementa el `epoch` del usuario; las siguientes ediciones de
        `usuario_de_token` verán que el token presentado lleva un epoch viejo
        y lo rechazarán. No requiere rotar el secreto global del server."""
        u = normalizar(username)
        with self._lock:
            reg = self._usuarios.get(u)
            if reg is None:
                return
            h = _hash_de_registro(reg) or MARCADOR_EXTERNO
            self._usuarios[u] = {"hash": h, "epoch": _epoch_de_registro(reg) + 1}
            self._guardar()

    def cambiar_password(self, username: str, password: str) -> bool:
        """Reemplaza la contraseña del usuario y revoca sus sesiones vivas.
        True si el usuario existía, False si no. Mantenido como API explícita
        para que el caller no tenga que reconstruir el registro a mano."""
        u = normalizar(username)
        with self._lock:
            if u not in self._usuarios:
                return False
            reg = self._usuarios[u]
            self._usuarios[u] = {
                "hash": hash_password(password),
                "epoch": _epoch_de_registro(reg) + 1,
            }
            self._guardar()
        return True

    def verificar(self, username: str, password: str) -> bool:
        """¿Usuario existe y la contraseña coincide? False si cualquiera falla."""
        registro = self._usuarios.get(normalizar(username))
        h = _hash_de_registro(registro)
        if h is None:
            return False
        return verificar_password(password, h)
