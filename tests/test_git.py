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


def test_commitear_crea_commit_con_autor(tmp_path) -> None:
    r = GitRepo(tmp_path)
    r.asegurar()
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    ok, detalle = r.commitear("primer commit", "ana", "ana@laidea.local")
    assert ok is True
    e = r.estado()
    assert e.cambios == 0
    assert "primer commit" in e.commits[0]
    log = subprocess.run(["git", "-C", str(tmp_path), "log", "-1", "--format=%an <%ae>"],
                          capture_output=True, text=True).stdout.strip()
    assert log == "ana <ana@laidea.local>"


def test_commitear_sin_cambios(tmp_path) -> None:
    r = GitRepo(tmp_path)
    r.asegurar()
    ok, detalle = r.commitear("nada", "ana", "ana@laidea.local")
    assert ok is False
    assert "cambios" in detalle


def test_commitear_git_deshabilitado() -> None:
    ok, detalle = GitRepo(None).commitear("x", "a", "a@b")
    assert ok is False and "no disponible" in detalle


def _remoto_local(tmp_path):
    """Un repo bare con un commit, hace de 'el repo del equipo' (sin red)."""
    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remoto)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(remoto), str(seed)], check=True)
    (seed / "hola.py").write_text("print('del remoto')\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(seed), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(seed), "-c", "user.email=a@b",
                    "-c", "user.name=a", "commit", "-q", "-m", "inicial"], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "HEAD"], check=True)
    return remoto


def test_clonar_reemplaza_el_workspace(tmp_path) -> None:
    ws = tmp_path / "ws"
    r = GitRepo(ws)
    r.asegurar()
    (ws / "viejo.py").write_text("basura anterior\n", encoding="utf-8")
    ok, detalle = r.clonar(str(_remoto_local(tmp_path)), "user", "token")
    assert ok is True, detalle
    assert (ws / "hola.py").read_text() == "print('del remoto')\n"
    assert not (ws / "viejo.py").exists()           # reemplazó, no fusionó
    assert "inicial" in r.estado().commits[0]


def test_clone_que_falla_no_destruye_el_workspace(tmp_path) -> None:
    ws = tmp_path / "ws"
    r = GitRepo(ws)
    r.asegurar()
    (ws / "importante.py").write_text("no me borres\n", encoding="utf-8")
    ok, _ = r.clonar(str(tmp_path / "no-existe.git"), "user", "token")
    assert ok is False
    assert (ws / "importante.py").read_text() == "no me borres\n"


def test_el_token_no_queda_en_git_config(tmp_path) -> None:
    ws = tmp_path / "ws"
    r = GitRepo(ws)
    ok, detalle = r.clonar(str(_remoto_local(tmp_path)), "user", "SECRETO-NO-FILTRAR")
    assert ok is True, detalle
    cfg = (ws / ".git" / "config").read_text()
    assert "SECRETO-NO-FILTRAR" not in cfg          # nunca en disco
    assert "remoto.git" in cfg                        # origin limpio sí


def test_token_no_aparece_en_el_detalle_de_error(tmp_path) -> None:
    ok, detalle = GitRepo(tmp_path / "ws").clonar(
        "https://host.invalido.laidea/x.git", "user", "TOKEN-XYZ-123"
    )
    assert ok is False
    assert "TOKEN-XYZ-123" not in detalle             # scrub / no-fuga


def test_push_lleva_el_commit_al_remoto(tmp_path) -> None:
    remoto = _remoto_local(tmp_path)
    ws = tmp_path / "ws"
    r = GitRepo(ws)
    assert r.clonar(str(remoto), "u", "t")[0] is True
    (ws / "nuevo.py").write_text("x = 1\n", encoding="utf-8")
    assert r.commitear("agrega nuevo", "ana", "ana@laidea.local")[0] is True
    ok, detalle = r.push("u", "t")
    assert ok is True, detalle
    # Clonar el remoto de nuevo, fresco: el commit llegó.
    verif = tmp_path / "verif"
    subprocess.run(["git", "clone", "-q", str(remoto), str(verif)], check=True)
    assert (verif / "nuevo.py").exists()


def test_push_sin_remoto_falla(tmp_path) -> None:
    ws = tmp_path / "ws"
    r = GitRepo(ws)
    r.asegurar()
    ok, detalle = r.push("u", "t")
    assert ok is False and "remoto" in detalle
