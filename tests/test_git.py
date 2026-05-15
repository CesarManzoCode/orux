"""Tests del núcleo Git (capa 8, 1/3). Usa un repo git real en tmp_path.

Como `DiskStorage`, esto toca el filesystem de verdad: el aislamiento lo da
`tmp_path` (un repo fresco por test). Lo crítico a fijar:
- `asegurar()` vuelve el workspace un repo git (idempotente);
- `estado()` reporta rama, cambios sin commitear y commits, antes y después
  de commitear desde "fuera" (simulando que el dev commitea en su terminal);
- deshabilitado (root None) nunca explota: `disponible=False`.
"""

import subprocess

from laidea.git import GitRepo


def _git(root, *args):
    """Simula al dev commiteando desde su terminal."""
    subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def test_deshabilitado_no_explota() -> None:
    e = GitRepo(None).estado()
    assert e.disponible is False
    assert e.rama == "" and e.cambios == 0 and e.commits == []


def test_asegurar_crea_repo_e_idempotente(tmp_path) -> None:
    r = GitRepo(tmp_path / "ws")
    r.asegurar()
    assert (tmp_path / "ws" / ".git").is_dir()
    r.asegurar()  # otra vez no rompe ni reinicializa de forma visible
    assert (tmp_path / "ws" / ".git").is_dir()


def test_estado_repo_vacio(tmp_path) -> None:
    # Repo recién init, sin commits: disponible, rama con nombre, 0 commits.
    e = GitRepo(tmp_path).estado()
    assert e.disponible is True
    assert isinstance(e.rama, str) and e.rama  # "main"/"master", no vacío
    assert e.commits == []


def test_estado_cuenta_cambios_sin_commitear(tmp_path) -> None:
    r = GitRepo(tmp_path)
    r.asegurar()
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    e = r.estado()
    assert e.cambios == 2  # dos archivos sin trackear
    assert e.commits == []


def test_estado_tras_commit_externo(tmp_path) -> None:
    # El dev commitea desde su terminal: la tool lo refleja (es solo lectura,
    # git es la fuente de verdad).
    r = GitRepo(tmp_path)
    r.asegurar()
    _git(tmp_path, "config", "user.email", "dev@laidea.local")
    _git(tmp_path, "config", "user.name", "dev")
    (tmp_path / "main.py").write_text("print('hola')\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "primer commit")

    e = r.estado()
    assert e.cambios == 0
    assert len(e.commits) == 1
    assert "primer commit" in e.commits[0]
