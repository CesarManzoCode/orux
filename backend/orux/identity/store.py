"""Registro de usuarios persistido. Núcleo de la capa 7.

Es a la identidad lo que `DiskStorage` es al workspace: el estado autoritativo
de "quién existe", guardado en disco para que sobreviva a reiniciar el server.
Mismo patrón de inyección de dependencias: recibe la ruta del archivo; el
server real la cablea, los tests usan `tmp_path`.

Decisiones de prototipo, documentadas porque no son obvias:

- **Un solo archivo JSON** `usuario -> registro de contraseña`. Suficiente
  para 2-50 personas (el público objetivo). Nada de base de datos todavía.
- **El usuario se normaliza** (trim + minúsculas): "Joaquin" y "joaquin" son
  el mismo, para que el ownership no se parta por mayúsculas.
- La contraseña nunca se guarda ni pasa por aquí en claro más de lo
  imprescindible: se delega de inmediato en `passwords` (PBKDF2 + sal).
"""

from __future__ import annotations

import json
import os
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
_USUARIO_MIN = 2
_USUARIO_MAX = 32
_USUARIO_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789._-+@")
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


class UserStore:
    def __init__(self, path: Path | str | None = None) -> None:
        # None = en memoria (tests), igual que DiskStorage/Ownership. Con ruta,
        # los usuarios sobreviven a reiniciar el server.
        self._path = Path(path) if path is not None else None
        # usuario_normalizado -> registro de contraseña (string autodescriptivo).
        self._usuarios: dict[str, str] = {}
        if self._path is not None and self._path.exists():
            try:
                self._usuarios = json.loads(
                    self._path.read_text(encoding="utf-8")
                )
            except (ValueError, OSError):
                # Archivo corrupto: arrancamos vacío en vez de tumbar el server.
                # En un prototipo es preferible "nadie registrado" a no arrancar.
                self._usuarios = {}

    def _guardar(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atómico (robustez B-varios): temporal + os.replace, igual que
        # ownership.json. Un crash a mitad de `write_text` dejaba
        # `users.json` truncado; al reiniciar, `__init__` traga el
        # ValueError y arranca con CERO usuarios — todo el equipo pierde su
        # cuenta en silencio. El rename atómico nunca deja el archivo a
        # medias: o están todos los usuarios viejos, o todos los nuevos.
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._usuarios), encoding="utf-8")
        os.replace(tmp, self._path)

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
        if u in self._usuarios:
            raise ValueError("ese usuario ya existe")
        self._usuarios[u] = hash_password(password)  # valida password vacía
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
        contraseña."""
        u = normalizar(username)
        if not u:
            raise ValueError("usuario inválido")
        if u not in self._usuarios:
            self._usuarios[u] = MARCADOR_EXTERNO
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

    def verificar(self, username: str, password: str) -> bool:
        """¿Usuario existe y la contraseña coincide? False si cualquiera falla."""
        registro = self._usuarios.get(normalizar(username))
        if registro is None:
            return False
        return verificar_password(password, registro)
