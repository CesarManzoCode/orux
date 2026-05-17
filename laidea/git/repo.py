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

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Script `GIT_ASKPASS`: git lo llama cuando un remoto pide credenciales. NO
# contiene el secreto — lo lee del entorno del subproceso (que vive solo
# durante esa llamada). Según qué pregunte git ("Username"/"Password") devuelve
# el usuario o el token. Así el token NUNCA va en argv, ni en la URL, ni en
# `.git/config`, ni queda cacheado.
_ASKPASS = (
    "#!/bin/sh\n"
    'case "$1" in\n'
    '  *[Uu]sername*) printf "%s" "$LAIDEA_GIT_USER" ;;\n'
    '  *) printf "%s" "$LAIDEA_GIT_TOKEN" ;;\n'
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
        self._root = Path(root) if root is not None else None

    def _run(self, *args: str) -> tuple[int, str]:
        """Corre `git <args>` en el repo. (returncode, stdout). Tolerante.

        Si git no está instalado (`FileNotFoundError`) devolvemos un código
        distinto de cero y stdout vacío: quien llame lo trata como "git no
        disponible", nunca como excepción que suba.
        """
        try:
            p = subprocess.run(
                ["git", *args],
                cwd=self._root,
                capture_output=True,
                text=True,
            )
            return p.returncode, p.stdout.strip()
        except (FileNotFoundError, OSError):
            return 1, ""

    def asegurar(self) -> None:
        """Garantiza que el workspace sea un repo git. Idempotente.

        Crea el directorio si no existe y hace `git init` si todavía no es un
        repo. No configura identidad ni hace commits: no commiteamos desde
        aquí. No falla si git no está (el `_run` lo absorbe).
        """
        if self._root is None:
            return
        self._root.mkdir(parents=True, exist_ok=True)
        if not (self._root / ".git").is_dir():
            self._run("init", "-q")

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
        - la salida se *scrubea*: si git llegara a eco el token, se reemplaza
          por `***` antes de devolverlo (no se loguea crudo nunca).
        """
        askpass = tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False
        )
        try:
            askpass.write(_ASKPASS)
            askpass.close()
            os.chmod(askpass.name, 0o700)
            env = {
                **os.environ,
                "GIT_ASKPASS": askpass.name,
                "GIT_TERMINAL_PROMPT": "0",
                "LAIDEA_GIT_USER": usuario,
                "LAIDEA_GIT_TOKEN": token,
            }
            try:
                p = subprocess.run(
                    ["git", "-c", "credential.helper=", *args],
                    cwd=cwd if cwd is not None else self._root,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                salida = (p.stdout + p.stderr).strip()
                rc = p.returncode
            except (FileNotFoundError, OSError):
                return 1, "git no disponible"
        finally:
            os.unlink(askpass.name)
        # Defensa en profundidad: aunque el token no debería aparecer, si
        # aparece NO sale de aquí en claro.
        if token:
            salida = salida.replace(token, "***")
        return rc, salida

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
        como argv (lista, sin shell): no hay inyección posible.
        """
        if self._root is None:
            return (False, "git no disponible")
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
        """
        if self._root is None:
            return (False, "git no disponible")
        tmp = Path(tempfile.mkdtemp(prefix="laidea-clone-"))
        destino = tmp / "repo"
        try:
            rc, out = self._git_cred(
                ["clone", url, str(destino)], usuario, token, cwd=tmp
            )
            if rc != 0:
                return (False, _detalle_remoto(out))
            # Éxito: ahora sí reemplazamos. Vaciamos el contenido del
            # workspace (NO el directorio en sí: puede ser un mount) y movemos
            # el repo clonado adentro, con su `.git` (origin limpio incluido).
            self._root.mkdir(parents=True, exist_ok=True)
            for hijo in self._root.iterdir():
                if hijo.is_dir() and not hijo.is_symlink():
                    shutil.rmtree(hijo)
                else:
                    hijo.unlink()
            for hijo in destino.iterdir():
                shutil.move(str(hijo), str(self._root / hijo.name))
            return (True, "repo clonado: reemplazó el workspace")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def push(
        self, usuario: str, token: str, url: str | None = None
    ) -> tuple[bool, str]:
        """Empuja el workspace a su remoto. `url` opcional re-apunta `origin`.

        No fusiona: si el remoto avanzó (non-fast-forward) el push se rechaza
        y lo decimos claro — traer/mergear es la parte difícil diferida, no se
        finge que anda. `origin` se setea SIN credenciales (van por askpass).
        """
        if self._root is None:
            return (False, "git no disponible")
        self.asegurar()
        if url:
            self._run("remote", "remove", "origin")
            self._run("remote", "add", "origin", url)
        rc_url, actual = self._run("remote", "get-url", "origin")
        if rc_url != 0 or not actual:
            return (False, "no hay remoto configurado (falta la URL)")
        rc, out = self._git_cred(["push", "origin", "HEAD"], usuario, token)
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
        ESTE equipo, p.ej. `laidea/<team_id>`), NUNCA a `main`. Devuelve
        (ok, detalle, url_pr).

        La rama es de PUBLICACIÓN: laidea es su único escritor; los humanos
        integran vía PR DESDE ella en GitHub (la tesis: integración, no
        reemplazo — laidea no fusiona). Por eso `--force-with-lease` con
        `fetch` previo: el workspace del equipo es la fuente de verdad
        (tras un clone destructivo la historia local cambia y un push
        normal sería non-ff para siempre); el lease igual RECHAZA si
        alguien commiteó a mano esa rama (no se debe: PR desde ella, no
        commits en ella) y se dice claro. No fusiona nada.
        """
        if self._root is None:
            return (False, "git no disponible", "")
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
