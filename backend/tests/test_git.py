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


# --- Capa 21: push a la rama del equipo + link de PR ---------------------

from laidea.git.repo import _url_pr  # noqa: E402


def test_url_pr_github_ssh_y_https() -> None:
    assert _url_pr("git@github.com:acme/app.git", "laidea/ef6a") == \
        "https://github.com/acme/app/pull/new/laidea/ef6a"
    assert _url_pr("https://github.com/acme/app", "laidea/x") == \
        "https://github.com/acme/app/pull/new/laidea/x"
    assert _url_pr("ssh://git@github.com/acme/app.git", "r") == \
        "https://github.com/acme/app/pull/new/r"


def test_url_pr_no_github_es_vacio() -> None:
    # No se inventa link para remotos que no son GitHub (gitlab, bare local).
    assert _url_pr("git@gitlab.com:acme/app.git", "r") == ""
    assert _url_pr("/tmp/repo-bare", "r") == ""
    assert _url_pr("", "r") == ""


def test_push_a_rama_no_toca_main(tmp_path) -> None:
    remoto = _remoto_local(tmp_path)
    ws = tmp_path / "ws"
    r = GitRepo(ws)
    assert r.clonar(str(remoto), "u", "t")[0] is True
    (ws / "nuevo.py").write_text("x = 1\n", encoding="utf-8")
    assert r.commitear("c", "ana", "ana@laidea.local")[0] is True
    ok, detalle, pr = r.push_a_rama("u", "t", "laidea/eq1")
    assert ok is True, detalle
    assert pr == ""  # remoto local, no github
    # El commit está en la rama del equipo, NO en la default (main).
    heads = subprocess.run(
        ["git", "ls-remote", "--heads", str(remoto)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "refs/heads/laidea/eq1" in heads
    verif = tmp_path / "verif"
    subprocess.run(["git", "clone", "-q", "--branch", "laidea/eq1",
                    str(remoto), str(verif)], check=True)
    assert (verif / "nuevo.py").exists()


def test_push_a_rama_idempotente_tras_reclone(tmp_path) -> None:
    # La rama es de publicación: re-pushear tras un clone destructivo
    # (historia local nueva) NO debe quedar bloqueado por non-ff.
    remoto = _remoto_local(tmp_path)
    ws = tmp_path / "ws"
    r = GitRepo(ws)
    r.clonar(str(remoto), "u", "t")
    (ws / "a.py").write_text("1\n", encoding="utf-8")
    r.commitear("c1", "ana", "ana@laidea.local")
    assert r.push_a_rama("u", "t", "laidea/eq1")[0] is True
    # Clone destructivo: historia local distinta.
    r.clonar(str(remoto), "u", "t")
    (ws / "b.py").write_text("2\n", encoding="utf-8")
    r.commitear("c2", "ana", "ana@laidea.local")
    ok, detalle, _ = r.push_a_rama("u", "t", "laidea/eq1")
    assert ok is True, detalle  # force-with-lease lo permite (rama propia)


def test_push_a_main_directo_sin_forzar(tmp_path) -> None:
    # Capa 21b: pushear a main DEBE seguir siendo posible (directo, sin
    # forzar). El usuario eligió "elegir rama", no "quitar main".
    remoto = _remoto_local(tmp_path)
    ws = tmp_path / "ws"
    r = GitRepo(ws)
    assert r.clonar(str(remoto), "u", "t")[0] is True
    (ws / "directo.py").write_text("x = 1\n", encoding="utf-8")
    assert r.commitear("c", "ana", "ana@laidea.local")[0] is True
    # rama=None => HEAD => la rama actual (main del clone): va a main.
    ok, detalle = r.push("u", "t")
    assert ok is True, detalle
    verif = tmp_path / "verif"
    subprocess.run(["git", "clone", "-q", str(remoto), str(verif)],
                   check=True)
    # clone default = main: el archivo está (se pusheó a main, no a rama).
    assert (verif / "directo.py").exists()


def test_push_a_rama_nombrada_sin_forzar(tmp_path) -> None:
    # push(rama="X") empuja a refs/heads/X SIN forzar (capa 21b: destino
    # directo elegible). El force-with-lease vive SOLO en push_a_rama
    # (la rama propia de laidea); a ramas ajenas nunca se fuerza.
    remoto = _remoto_local(tmp_path)
    ws = tmp_path / "ws"
    r = GitRepo(ws)
    r.clonar(str(remoto), "u", "t")
    (ws / "f.py").write_text("1\n", encoding="utf-8")
    r.commitear("c", "ana", "ana@laidea.local")
    assert r.push("u", "t", None, "develop")[0] is True
    heads = subprocess.run(
        ["git", "ls-remote", "--heads", str(remoto)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "refs/heads/develop" in heads


# --- Blindaje capa 10: la URL/rama del cliente no debe ser un vector RCE ---

from laidea.git.repo import _url_segura, _rama_segura  # noqa: E402


def test_url_rechaza_transporte_ext_y_fd() -> None:
    # `ext::sh -c "..."` haría que git ejecute un comando arbitrario en el
    # servidor: ejecución remota por cualquier miembro de un equipo.
    assert _url_segura('ext::sh -c "touch /tmp/pwned"') is False
    assert _url_segura("fd::17/foo") is False
    assert _url_segura("EXT::algo") is False  # case-insensitive


def test_url_rechaza_inyeccion_de_flag_y_vacio() -> None:
    assert _url_segura("--upload-pack=/bin/sh") is False
    assert _url_segura("-oProxyCommand=evil") is False
    assert _url_segura("") is False
    assert _url_segura("   ") is False


def test_url_acepta_remotos_legitimos_y_paths_locales() -> None:
    assert _url_segura("https://github.com/acme/app.git") is True
    assert _url_segura("git@github.com:acme/app.git") is True
    assert _url_segura("ssh://git@host/acme/app") is True
    assert _url_segura("/tmp/repo-bare") is True  # los tests clonan así


def test_rama_rechaza_caracteres_raros_y_dotdot() -> None:
    assert _rama_segura("laidea/ef6a") is True
    assert _rama_segura("main") is True
    assert _rama_segura("..") is False
    assert _rama_segura("a/../b") is False
    assert _rama_segura("-flag") is False
    assert _rama_segura("rama con espacio") is False
    assert _rama_segura("") is False


def test_clone_con_url_insegura_no_invoca_git(tmp_path) -> None:
    r = GitRepo(tmp_path / "ws")
    ok, detalle = r.clonar('ext::sh -c "echo hax"', "u", "t")
    assert ok is False
    assert "no válida" in detalle
