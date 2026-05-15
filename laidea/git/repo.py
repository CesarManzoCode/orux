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

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


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
