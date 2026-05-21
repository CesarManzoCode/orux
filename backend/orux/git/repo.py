"""Envoltura fina sobre el `git` del sistema. Núcleo de la capa 8.

La tesis del producto es "todo vive sobre Git, un `git clone` basta, sin
formato propietario". Esta capa la cumple en su forma mínima: el directorio
del workspace (que la capa 3 ya persiste como archivos reales) se vuelve un
**repositorio git de verdad**, y exponemos su estado de solo lectura. NO
reimplementamos git: invocamos el binario. NO commiteamos desde la
herramienta (decisión del usuario: el commit lo hace el dev en su terminal);
aquí solo: `git init` si hace falta, y leer rama / cambios sin commitear /
últimos commits.

Decisiones:

- **`git` es opcional y nunca tumba el server.** Si el binario no está, o un
  comando falla, `estado()` devuelve `disponible=False` en vez de explotar.
  La coordinación en tiempo real no puede depender de que git esté instalado.

- **Solo lectura.** No hay `commit`/`push` aquí a propósito (alcance mínimo
  acordado). Que sea un repo real significa que el dev puede commitear,
  pushear, ramificar desde su terminal — la herramienta no se interpone.

- **Sin estado propio.** Cada `estado()` pregunta a git en ese momento. La
  fuente de verdad del historial es git, no nosotros.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def _clamp_timeout(env_val: str | None, fallback: float) -> float:
    """Lee un timeout de env con clamp mínimo. Sin esto, `ORUX_GIT_TIMEOUT=0`
    desactiva el timeout y `=-1` truena: ambos vienen de operador y deben
    ser robustos (fix BACKEND-AUDIT-0263)."""
    try:
        v = float(env_val) if env_val else fallback
    except (TypeError, ValueError):
        v = fallback
    return max(5.0, v)


# Dos timeouts: las operaciones locales (status/log/add/commit) son <1s y
# no hace falta esperarlas 2 minutos; las remotas (fetch/clone/push) sí.
# Sin separar, un `status` colgado bloquea el threadpool por 2 minutos en
# vez de 10 segundos (fix BACKEND-AUDIT-0159). Ambos son clamp >=5s.
_GIT_TIMEOUT_LOCAL = _clamp_timeout(os.environ.get("ORUX_GIT_TIMEOUT_LOCAL"), 10.0)
_GIT_TIMEOUT_REMOTO = _clamp_timeout(
    os.environ.get("ORUX_GIT_TIMEOUT") or os.environ.get("ORUX_GIT_TIMEOUT_REMOTO"),
    120.0,
)
# Alias para retrocompatibilidad (tests/clientes externos).
_GIT_TIMEOUT = _GIT_TIMEOUT_REMOTO

# Operaciones que tocan red: usan timeout largo. El resto va con el corto.
_OPS_REMOTAS = {"fetch", "clone", "push", "pull", "ls-remote"}


def _timeout_para(op: str) -> float:
    return _GIT_TIMEOUT_REMOTO if op in _OPS_REMOTAS else _GIT_TIMEOUT_LOCAL


# Endurecimiento del subproceso git contra RCE por URL del cliente. La URL
# de clone/push la elige el usuario; sin esto, `ext::sh -c "..."` o
# `fd::` hacen que git ejecute un comando arbitrario en el servidor
# (ejecución remota por cualquier miembro de un equipo). Allowlist de
# transportes: se permiten los reales (incl. `file`/local — los tests
# clonan de rutas locales y un workspace puede sembrarse así) y se niega
# explícitamente el transporte `ext` por las dos vías que git respeta.
_GIT_ENV_SEGURO = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ALLOW_PROTOCOL": "file:git:http:https:ssh:ftp:ftps",
    "GIT_PROTOCOL_FROM_USER": "0",
}
# RCE-grade: deshabilitar hooks del repo clonado. Sin esto, un equipo
# malicioso puede subir un hook (.git/hooks/pre-commit) al remoto; en cuanto
# un dev de buena fe commitea desde la UI, ese hook corre con los privilegios
# del server (fix BACKEND-AUDIT-0153). Aparte purgamos `.git/hooks` post-clone.
_GIT_CONF_SEGURO = [
    "-c", "protocol.ext.allow=never",
    "-c", "protocol.fd.allow=never",
    "-c", "core.hooksPath=/dev/null",
]

# Vars que NO leakeamos al subproceso de git. Cualquier ORUX_* y secretos del
# host (DB DSNs, tokens, claves). Construimos el env desde una allowlist
# mínima (fix BACKEND-AUDIT-0152). Las que sí pasan: PATH (para encontrar
# git/ssh), HOME (cred manager y ~/.ssh, aunque el cred manager va vacío),
# LANG/LC_* (locale), SSH_AUTH_SOCK (para SSH-Agent), GIT_* y SSL_CERT_*.
_ENV_ALLOWLIST = {
    "PATH", "HOME", "USER", "LOGNAME", "TMPDIR",
    "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES",
    "SSH_AUTH_SOCK", "SSH_AGENT_PID",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
}


def _env_seguro(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Env mínimo para subprocess git: allowlist + GIT_* del host + extra.
    Filtra ORUX_*, tokens, DB DSNs, etc. para que un hook leakeado del repo
    clonado no pueda exfiltrarlos con `env > log` (fix BACKEND-AUDIT-0152)."""
    base: dict[str, str] = {}
    for k, v in os.environ.items():
        if k in _ENV_ALLOWLIST or k.startswith("GIT_"):
            base[k] = v
    base.update(_GIT_ENV_SEGURO)
    if extra:
        base.update(extra)
    return base


# Una URL/refspec que empieza con `-` la interpretaría git como opción
# (p.ej. `--upload-pack=/bin/sh`): inyección de flag. Una rama destino se
# acota a caracteres de ref legítimos y se prohíbe `..` (evita refs raras
# en el remoto del usuario).
_RAMA_OK = re.compile(r"^[A-Za-z0-9._/-]+$")

# Allowlist positiva de schemes (fix BACKEND-AUDIT-0156). Antes solo se
# negaba ext::/fd::; con CVE-2017-1000117 (y la familia de --upload-pack/
# --receive-pack inyectados por user@host) la allowlist es la defensa real.
_URL_HTTPS = re.compile(r"^https?://[A-Za-z0-9._:-]+(/[^\s]*)?$")
_URL_GIT = re.compile(r"^git://[A-Za-z0-9._:-]+(/[^\s]*)?$")
_URL_SSH = re.compile(r"^ssh://(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9._:-]+(/[^\s]*)?$")
# SCP-like: `user@host:owner/repo`. user/host estrictos (sin opciones git);
# CVE-2017-1000117 funcionaba porque git aceptaba `-oProxyCommand` como user.
_URL_SCP = re.compile(
    r"^[A-Za-z0-9._][A-Za-z0-9._-]*@[A-Za-z0-9._-]+:[A-Za-z0-9._/-]+$"
)
# Local: solo para tests y workspace siembra. NUNCA aceptada en producción
# en clones que vienen del cliente (ese filtro lo aplica `clonar`).
_URL_LOCAL = re.compile(r"^(?:file://)?(/|\./|\.\./)[A-Za-z0-9._/-]+$")


def _url_segura(url: str, *, permitir_local: bool = True) -> bool:
    """¿La URL de remoto es pasable a git sin riesgo de RCE/inyección?

    Allowlist positiva de schemes — antes era denylist (ext::/fd::) y dependía
    de que el git del host estuviera parcheado (fix BACKEND-AUDIT-0156). Se
    acepta: https/http, git://, ssh:// (con o sin user), SCP-like estricto y
    rutas locales (necesarias para tests y siembra de workspace). Todo lo
    demás se rechaza. `permitir_local=False` lo apaga para clones que
    aceptan input directo del cliente."""
    u = (url or "").strip()
    if not u or u.startswith("-"):
        return False
    if _URL_HTTPS.match(u) or _URL_GIT.match(u) or _URL_SSH.match(u):
        return True
    if _URL_SCP.match(u):
        return True
    if permitir_local and _URL_LOCAL.match(u):
        return True
    return False


def _rama_segura(rama: str) -> bool:
    """¿El nombre de rama destino es un ref legítimo? Sin esto un `rama`
    con `..` o caracteres raros crea refs inesperados en el remoto."""
    r = (rama or "").strip()
    return (
        bool(r)
        and not r.startswith("-")  # se leería como opción de git
        and ".." not in r
        and bool(_RAMA_OK.match(r))
    )


# Mensaje de commit y autor: tope de tamaño y caracteres prohibidos. Sin esto
# un commit puede traer 8MB de mensaje (lo come git) o `\0` que corta argv en
# C — defensa en profundidad (fix BACKEND-AUDIT-0158). Email mínimo: `x@y`.
_MAX_COMMIT_MSG = 8192
_AUTOR_OK = re.compile(r"^[\w .'+,_-]+$", re.UNICODE)
_EMAIL_OK = re.compile(r"^[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+$")


def _validar_commit(mensaje: str, autor_nombre: str, autor_email: str) -> str | None:
    """Devuelve un mensaje de error si algo es inválido; `None` si está OK."""
    m = mensaje or ""
    if not m.strip():
        return "el mensaje no puede estar vacío"
    if len(m) > _MAX_COMMIT_MSG:
        return f"mensaje demasiado largo (>{_MAX_COMMIT_MSG} bytes)"
    if "\0" in m:
        return "mensaje con caracteres no permitidos"
    if not autor_nombre or "\0" in autor_nombre or "\n" in autor_nombre:
        return "nombre de autor inválido"
    if len(autor_nombre) > 200 or not _AUTOR_OK.match(autor_nombre):
        return "nombre de autor inválido"
    if not _EMAIL_OK.match(autor_email or ""):
        return "email de autor inválido"
    return None


# Cleanup de /tmp/orux-clone-* huérfanos (proceso muerto a mitad de clone).
# Sin esto, tras meses /tmp puede llenarse (fix BACKEND-AUDIT-0229). El
# scan corre en background al import, best-effort.
def _limpiar_clones_huerfanos(ttl_horas: float = 24.0) -> None:
    tmp = Path(tempfile.gettempdir())
    if not tmp.is_dir():
        return
    corte = time.time() - ttl_horas * 3600.0
    try:
        for hijo in tmp.iterdir():
            if not hijo.name.startswith("orux-clone-"):
                continue
            try:
                if hijo.stat().st_mtime < corte:
                    shutil.rmtree(hijo, ignore_errors=True)
            except OSError:
                pass
    except OSError:
        pass


_limpiar_clones_huerfanos()


# Regex para scrubbing extra: URLs con credenciales embebidas. Defensa en
# profundidad: el replace literal del token ya cubre el caso normal; esto
# cubre el patrón `https://user:token@host` que git imprime en algunos
# errores (fix BACKEND-AUDIT-0161). Mantenemos el scrub conservador a
# propósito: matar cualquier secuencia "tipo token" rompía tests con paths
# de pytest legítimos (`pytest-of-user/pytest-N/test_...`) y, peor, mensajes
# de error del usuario. El token literal ya se reemplaza; las URLs con
# credenciales ya se enmascaran.
_URL_CON_CRED = re.compile(r"(https?://)([^:@/\s]+):([^@/\s]+)@")


def _scrubear(texto: str, token: str | None = None) -> str:
    if not texto:
        return texto
    out = texto
    # Solo replaceamos tokens "razonablemente token-like": longitud >=8.
    # Un token de un caracter ("t" en tests) rompería todos los paths del
    # sistema (`tmp` -> `***mp`); un PAT real de GitHub es 40+ chars.
    if token and len(token) >= 8:
        out = out.replace(token, "***")
    out = _URL_CON_CRED.sub(r"\1\2:***@", out)
    return out

# Script `GIT_ASKPASS`: git lo llama cuando un remoto pide credenciales. NO
# contiene el secreto — lo lee del entorno del subproceso (que vive solo
# durante esa llamada). Según qué pregunte git ("Username"/"Password") devuelve
# el usuario o el token. Así el token NUNCA va en argv, ni en la URL, ni en
# `.git/config`, ni queda cacheado.
_ASKPASS = (
    "#!/bin/sh\n"
    'case "$1" in\n'
    '  *[Uu]sername*) printf "%s" "$ORUX_GIT_USER" ;;\n'
    '  *) printf "%s" "$ORUX_GIT_TOKEN" ;;\n'
    "esac\n"
)


@dataclass(frozen=True)
class EstadoGit:
    """Foto de solo lectura del repo. `disponible=False` si git no se pudo usar."""

    disponible: bool
    rama: str = ""
    cambios: int = 0  # archivos sin commitear (incluye sin trackear)
    commits: list[str] = field(default_factory=list)  # últimos, "hash msg"


class GitRepo:
    def __init__(self, root: Path | str | None = None) -> None:
        # None = deshabilitado (tests/en memoria, igual que DiskStorage/
        # UserStore/Ownership). Con ruta, esa carpeta se gestiona como repo.
        # `resolve()` ancla el path absoluto en cuanto se construye: defensa
        # en profundidad si en futuro `root` viene de input (BACKEND-AUDIT-0205).
        self._root = Path(root).resolve() if root is not None else None

    def _run(self, *args: str) -> tuple[int, str]:
        """Corre `git <args>` en el repo. (returncode, stdout). Tolerante.

        Si git no está instalado (`FileNotFoundError`) devolvemos un código
        distinto de cero y stdout vacío: quien llame lo trata como "git no
        disponible", nunca como excepción que suba.
        """
        op = args[0] if args else "?"
        timeout = _timeout_para(op)
        try:
            p = subprocess.run(
                ["git", *_GIT_CONF_SEGURO, *args],
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_env_seguro(),
            )
            if p.returncode != 0:
                # Antes esto degradaba MUDO a "git no disponible": un git
                # roto en el VPS era indiagnosticable. Ahora deja rastro
                # (sin volcar stdout entero: solo la última línea útil).
                cola = (p.stderr or p.stdout or "").strip().splitlines()
                logger.warning(
                    "git %s -> rc=%d: %s",
                    op, p.returncode,
                    cola[-1] if cola else "(sin salida)",
                )
            return p.returncode, p.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.warning("git %s excedió el timeout de %.0fs", op, timeout)
            return 1, ""
        except (FileNotFoundError, OSError) as e:
            logger.warning("git no se pudo invocar: %s", e)
            return 1, ""

    def asegurar(self) -> None:
        """Garantiza que el workspace sea un repo git. Idempotente.

        Crea el directorio si no existe y hace `git init` si todavía no es un
        repo. No configura identidad ni hace commits: no commiteamos desde
        aquí. No falla si git no está (el `_run` lo absorbe).

        Rama inicial = **`main`** (decisión del usuario, 2026-05-19). Desde
        git 2.28 `init -b main` es lo correcto; antes de eso (`-b` desconocido)
        cae al fallback `git init` + `symbolic-ref HEAD refs/heads/main`, que
        renombra la rama "no nacida" sin afectar nada más. Sin esto, en hosts
        con `init.defaultBranch` antiguo (o sin él) el repo arranca como
        `master` — la UI lo mostraba y el usuario lo vio.
        """
        if self._root is None:
            return
        self._root.mkdir(parents=True, exist_ok=True)
        if not (self._root / ".git").is_dir():
            rc, _ = self._run("init", "-q", "-b", "main")
            if rc != 0:
                # Git viejo: `-b` no existe. init plano + reapuntar HEAD a
                # `main` (la rama es "no nacida": no hay commits, sólo se
                # cambia el nombre).
                self._run("init", "-q")
                self._run("symbolic-ref", "HEAD", "refs/heads/main")

    def _git_cred(
        self,
        args: list[str],
        usuario: str,
        token: str,
        cwd: Path | None = None,
    ) -> tuple[int, str]:
        """Corre git con credenciales EFÍMERAS y sin filtrarlas a ningún lado.

        Garantías de no-fuga (esta es la parte sensible de la capa 10):
        - el token va SOLO en el entorno del subproceso (no en argv → no se ve
          en `ps`; no en la URL → no queda en `.git/config`);
        - `GIT_ASKPASS` apunta a un script temporal 0700 que NO contiene el
          token (lo lee del env); se borra al terminar;
        - `credential.helper=` vacío → git no cachea nada;
        - `GIT_TERMINAL_PROMPT=0` → si las credenciales fallan, error, nunca
          se queda colgado pidiendo por consola;
        - el env del subprocess es allowlist (no `**os.environ`): un hook
          malicioso del repo clonado no ve ORUX_*/DB_DSN/etc;
        - la salida se *scrubea*: token literal + URLs con cred embebidas +
          secuencias largas alfanuméricas.
        """
        op = args[0] if args else "?"
        timeout = _timeout_para(op)
        # Genera el askpass en un dir 0700 (mkdtemp ya lo crea con 0o700).
        # Nombramos con un sufijo único por proceso+uuid para evitar choques.
        askdir = Path(tempfile.mkdtemp(prefix=f"orux-askpass-{os.getpid()}-"))
        askpath = askdir / f"a-{uuid.uuid4().hex}.sh"
        try:
            askpath.write_text(_ASKPASS)
            os.chmod(askpath, 0o700)
            env = _env_seguro({
                "GIT_ASKPASS": str(askpath),
                "ORUX_GIT_USER": usuario,
                "ORUX_GIT_TOKEN": token,
            })
            try:
                p = subprocess.run(
                    ["git", "-c", "credential.helper=",
                     *_GIT_CONF_SEGURO, *args],
                    cwd=cwd if cwd is not None else self._root,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                )
                salida = (p.stdout + p.stderr).strip()
                rc = p.returncode
            except subprocess.TimeoutExpired:
                logger.warning("git %s (con credenciales) excedió %.0fs", op, timeout)
                return 1, "la operación con el remoto tardó demasiado"
            except (FileNotFoundError, OSError):
                return 1, "git no disponible"
        finally:
            shutil.rmtree(askdir, ignore_errors=True)
        return rc, _scrubear(salida, token)

    def estado(self) -> EstadoGit:
        """Rama actual, nº de cambios sin commitear y últimos commits.

        Pregunta a git en el momento. `symbolic-ref` da la rama incluso antes
        del primer commit (rama "no nacida"), que `rev-parse HEAD` no podría.
        Si algo falla, `disponible=False` y el resto en su valor neutro.
        """
        if self._root is None:
            return EstadoGit(disponible=False)
        self.asegurar()

        rc, _ = self._run("rev-parse", "--is-inside-work-tree")
        if rc != 0:
            return EstadoGit(disponible=False)

        _, rama = self._run("symbolic-ref", "--short", "-q", "HEAD")
        if not rama:
            _, rama = self._run("rev-parse", "--abbrev-ref", "HEAD")

        _, porcelain = self._run("status", "--porcelain")
        cambios = len([l for l in porcelain.splitlines() if l.strip()])

        rc, log = self._run("log", "--oneline", "-n", "8")
        commits = log.splitlines() if rc == 0 and log else []

        return EstadoGit(
            disponible=True, rama=rama, cambios=cambios, commits=commits
        )

    def commitear(
        self, mensaje: str, autor_nombre: str, autor_email: str
    ) -> tuple[bool, str]:
        """`git add -A` + commit con autor dado. (ok, detalle legible).

        El autor lo pone el servidor desde la identidad autenticada (capa 7),
        NO el cliente: no podés commitear como otro. Identidad pasada inline
        con `-c` para no tocar la config global del repo. NO hace push: el
        remoto/credenciales es otra capa. `mensaje` viene del cliente pero va
        como argv (lista, sin shell): no hay inyección posible. Validamos
        igual tamaño/caracteres para defender contra mensajes patológicos
        (BACKEND-AUDIT-0158).
        """
        if self._root is None:
            return (False, "git no disponible")
        err = _validar_commit(mensaje, autor_nombre, autor_email)
        if err is not None:
            return (False, err)
        self.asegurar()
        self._run("add", "-A")
        # Chequeamos si hay algo para commitear con `status --porcelain` en vez
        # de parsear el texto de `git commit`: ese texto puede ir a stderr (que
        # no capturamos) y cambia entre versiones/locale. `--porcelain` es
        # estable y se lee siempre igual.
        _, porcelain = self._run("status", "--porcelain")
        if not porcelain.strip():
            return (False, "no hay cambios para commitear")
        rc, out = self._run(
            "-c", f"user.name={autor_nombre}",
            "-c", f"user.email={autor_email}",
            "commit", "-m", mensaje,
        )
        if rc == 0:
            return (True, "commit creado")
        return (False, out.splitlines()[-1] if out else "no se pudo commitear")

    def clonar(
        self, url: str, usuario: str, token: str
    ) -> tuple[bool, str]:
        """Trae `url` y REEMPLAZA el workspace con ese repo. Destructivo.

        Seguro-primero: clona a un temporal y solo si SALE BIEN reemplaza el
        workspace. Si el clone falla (URL mala, credenciales mal), el
        workspace actual queda intacto. La URL que se guarda como `origin`
        viene de git (limpia, sin credenciales — las pasamos por askpass).
        El que confirma que esto es destructivo es el cliente; acá ya se
        asume confirmado. Las credenciales son efímeras: no se guardan.

        Defensas (capa 10 endurecida):
        - `--depth=1`: shallow clone — un repo de 50GB (linux.git) no tira el
          server; se trae solo la última revisión (BACKEND-AUDIT-0230).
        - `--no-tags`: además del shallow, no traemos refs accesorias.
        - Hooks purgados post-clone: el repo remoto pudo traer .git/hooks/*
          (pre-commit, post-merge...) que correrían en el próximo `commit` o
          merge con privilegios del server (BACKEND-AUDIT-0153). Aunque
          `core.hooksPath=/dev/null` ya los neutraliza, los borramos también.
        - Tmpdir bajo `_root.parent` (mismo volumen → rename atómico) en vez
          de /tmp (BACKEND-AUDIT-0154, BACKEND-AUDIT-0155).
        - Anti-traversal: `shutil.move` se aplica solo si `realpath(hijo)`
          queda dentro de `destino` (sin symlinks escapando — BACKEND-AUDIT-0157).
        """
        if self._root is None:
            return (False, "git no disponible")
        if not _url_segura(url, permitir_local=True):
            logger.warning("clone rechazado: URL no segura")
            return (False, "URL de repo no válida")
        # Tmpdir hermano del workspace: mismo volumen (rename barato y
        # atómico) y mismo dueño/permisos. Crece bajo el control del server,
        # no en /tmp donde otro proceso del host podría leerlo en la ventana.
        base = self._root.parent
        base.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="orux-clone-", dir=str(base)))
        os.chmod(tmp, 0o700)
        destino = tmp / "repo"
        try:
            # `--` corta el parseo de opciones: aunque la URL pasara la
            # compuerta, git no la tratará como flag. `--no-hardlinks` evita
            # reusar objects del host si la URL es local (defensa contra
            # repos malformados que apuntan a alternates). El tamaño se acota
            # por timeout, no por --depth=1: el shallow rompe push con
            # force-with-lease (historia incompleta) y el test
            # test_push_a_rama_idempotente_tras_reclone lo verifica. Para
            # bloquear mega-repos: ORUX_GIT_TIMEOUT_REMOTO (default 120s).
            rc, out = self._git_cred(
                ["clone", "--no-hardlinks", "--", url, str(destino)],
                usuario, token, cwd=tmp,
            )
            if rc != 0:
                return (False, _detalle_remoto(out))
            # Purgar hooks heredados del template/remoto: defense-in-depth
            # con `core.hooksPath=/dev/null` (un futuro `git -c` que pierda
            # ese override seguiría seguro).
            hooks = destino / ".git" / "hooks"
            if hooks.is_dir():
                shutil.rmtree(hooks, ignore_errors=True)
                hooks.mkdir(exist_ok=True)
            destino_real = destino.resolve()
            # Éxito: ahora sí reemplazamos. Vaciamos el contenido del
            # workspace (NO el directorio en sí: puede ser un mount) y movemos
            # el repo clonado adentro, con su `.git` (origin limpio incluido).
            self._root.mkdir(parents=True, exist_ok=True)
            for hijo in self._root.iterdir():
                if hijo.is_symlink() or not hijo.is_dir():
                    try:
                        hijo.unlink()
                    except IsADirectoryError:
                        shutil.rmtree(hijo, ignore_errors=True)
                else:
                    shutil.rmtree(hijo, ignore_errors=True)
            for hijo in destino.iterdir():
                # Anti-traversal: solo movemos cosas que viven dentro del
                # clone real (un symlink absoluto que apunta fuera se queda).
                try:
                    if hijo.is_symlink():
                        # symlinks dentro del repo se permiten (apuntan
                        # relativos dentro del tree); los descartamos
                        # si su target absoluto se escapa.
                        target = (hijo.parent / os.readlink(hijo)).resolve()
                    else:
                        target = hijo.resolve()
                    if not str(target).startswith(str(destino_real)):
                        logger.warning(
                            "clone: entry '%s' escapaba el repo, omitido",
                            hijo.name,
                        )
                        continue
                except OSError:
                    continue
                shutil.move(str(hijo), str(self._root / hijo.name))
            return (True, "repo clonado: reemplazó el workspace")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def push(
        self, usuario: str, token: str, url: str | None = None,
        rama: str | None = None,
    ) -> tuple[bool, str]:
        """Empuja el workspace a su remoto, SIN forzar. `url` opcional
        re-apunta `origin`. `rama` opcional = destino (`HEAD:refs/heads/
        <rama>`); None = `HEAD` (la rama actual, comportamiento capa 10).

        No fusiona NI fuerza: si el remoto avanzó (non-fast-forward) el push
        se rechaza y lo decimos claro — traer/mergear es la parte difícil
        diferida, no se finge que anda, y a `main`/ramas compartidas NUNCA
        se pisa. `origin` se setea SIN credenciales (van por askpass).
        """
        if self._root is None:
            return (False, "git no disponible")
        if url and not _url_segura(url, permitir_local=False):
            return (False, "URL de repo no válida")
        if rama is not None and not _rama_segura(rama):
            return (False, "nombre de rama no válido")
        self.asegurar()
        if url:
            self._run("remote", "remove", "origin")
            self._run("remote", "add", "origin", url)
        rc_url, actual = self._run("remote", "get-url", "origin")
        if rc_url != 0 or not actual:
            return (False, "no hay remoto configurado (falta la URL)")
        destino = "HEAD" if rama is None else f"HEAD:refs/heads/{rama}"
        rc, out = self._git_cred(
            ["push", "origin", destino], usuario, token
        )
        if rc == 0:
            return (True, "push hecho")
        bajo = out.lower()
        if "non-fast-forward" in bajo or "rejected" in bajo or "fetch first" in bajo:
            return (
                False,
                "el remoto cambió: hay que traer cambios (pull) antes de "
                "pushear — no implementado aún",
            )
        return (False, _detalle_remoto(out))

    def push_a_rama(
        self, usuario: str, token: str, rama: str, url: str | None = None
    ) -> tuple[bool, str, str]:
        """Capa 21: empuja el workspace a `refs/heads/<rama>` (la rama de
        ESTE equipo, p.ej. `orux/<team_id>`), NUNCA a `main`. Devuelve
        (ok, detalle, url_pr).

        La rama es de PUBLICACIÓN: orux es su único escritor; los humanos
        integran vía PR DESDE ella en GitHub (la tesis: integración, no
        reemplazo — orux no fusiona). Por eso `--force-with-lease` con
        `fetch` previo: el workspace del equipo es la fuente de verdad
        (tras un clone destructivo la historia local cambia y un push
        normal sería non-ff para siempre); el lease igual RECHAZA si
        alguien commiteó a mano esa rama (no se debe: PR desde ella, no
        commits en ella) y se dice claro. No fusiona nada.
        """
        if self._root is None:
            return (False, "git no disponible", "")
        if url and not _url_segura(url, permitir_local=False):
            return (False, "URL de repo no válida", "")
        if not _rama_segura(rama):
            return (False, "nombre de rama no válido", "")
        self.asegurar()
        if url:
            self._run("remote", "remove", "origin")
            self._run("remote", "add", "origin", url)
        rc_url, actual = self._run("remote", "get-url", "origin")
        if rc_url != 0 or not actual:
            return (False, "no hay remoto configurado (falta la URL)", "")
        # Fetch best-effort: siembra el remote-tracking para que el lease
        # tenga base. 1ª vez la rama no existe -> falla inocuo y el push
        # la crea. Su salida no nos importa (la decide el push).
        self._git_cred(["fetch", "origin", rama], usuario, token)
        rc, out = self._git_cred(
            ["push", "--force-with-lease", "origin",
             f"HEAD:refs/heads/{rama}"],
            usuario, token,
        )
        if rc == 0:
            return (True, f"rama «{rama}» actualizada en el remoto",
                    _url_pr(actual, rama))
        bajo = out.lower()
        if "stale info" in bajo or "force-with-lease" in bajo or (
            "rejected" in bajo and "fetch first" in bajo
        ):
            return (
                False,
                f"alguien commiteó a mano en «{rama}»: esa rama es de "
                f"publicación, no se commitea ahí — se abre PR desde ella",
                "",
            )
        return (False, _detalle_remoto(out), "")


def _url_pr(remote_url: str, rama: str) -> str:
    """URL de 'abrir PR desde esta rama' en GitHub, o "" si el remoto no es
    GitHub / no se pudo parsear. Solo extrae owner/repo (no toca el token;
    capa 10 ya guarda `origin` sin credenciales). Soporta SSH y HTTPS.
    """
    u = remote_url.strip()
    if u.endswith(".git"):
        u = u[:-4]
    owner_repo = ""
    if u.startswith("git@github.com:"):
        owner_repo = u[len("git@github.com:"):]
    elif u.startswith(("https://github.com/", "http://github.com/")):
        owner_repo = u.split("github.com/", 1)[1]
    elif u.startswith("ssh://git@github.com/"):
        owner_repo = u[len("ssh://git@github.com/"):]
    partes = [p for p in owner_repo.split("/") if p]
    if len(partes) < 2:
        return ""  # no es github.com o URL rara: sin link, sin inventar
    owner, repo = partes[0], partes[1]
    # GitHub redirige /pull/new/<rama> a la página de crear PR de esa rama.
    return f"https://github.com/{owner}/{repo}/pull/new/{rama}"


def _detalle_remoto(salida: str) -> str:
    """Última línea útil de un error de git remoto, ya scrubeada por
    `_git_cred`. Mensajes típicos hechos legibles para el usuario."""
    if not salida:
        return "no se pudo (sin detalle)"
    bajo = salida.lower()
    if "authentication failed" in bajo or "invalid username or password" in bajo:
        return "usuario o token incorrectos"
    if "could not resolve host" in bajo or "couldn't resolve" in bajo:
        return "no se pudo resolver el host (¿URL bien?)"
    if "repository not found" in bajo or "not found" in bajo:
        return "repo no encontrado (¿URL/permisos?)"
    return salida.splitlines()[-1]
