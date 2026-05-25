# Adapter: Git

`backend/orux/adapters/outbound/git/binary.py` envuelve el binario `git` del sistema. Cumple `GitPort`.

Es la pieza más endurecida de seguridad de todo el backend. La URL del remoto y el token vienen del cliente; sin las defensas que detallo abajo, un atacante con cuenta podría ejecutar comandos arbitrarios en el server.

## Operaciones expuestas

```python
class GitRepo:  # alias GitBinaryAdapter
    def __init__(self, root: Path | str | None = None): ...
    def asegurar(self) -> None
    def estado(self) -> EstadoGit
    def commitear(self, mensaje, autor_nombre, autor_email) -> tuple[bool, str]
    def clonar(self, url, usuario, token) -> tuple[bool, str]                # destructivo
    def push(self, usuario, token, url=None, rama=None) -> tuple[bool, str]
    def push_a_rama(self, usuario, token, rama, url=None) -> tuple[bool, str, str]
```

`None` para `root` = deshabilitado (tests/en memoria). El composition root usa `GitRepo(ws_dir)` con el dir del workspace del equipo.

## `estado() -> EstadoGit`

Pregunta a git en el momento. Sin estado propio.

```python
@dataclass(frozen=True)
class EstadoGit:  # vive en ports/git.py
    disponible: bool       # False si git falló (no instalado, permisos, etc.)
    rama: str = ""
    cambios: int = 0       # archivos sin commitear (incluye sin trackear)
    commits: list[str] = []  # últimos 8, "hash msg"
```

Combinación de `git rev-parse --is-inside-work-tree`, `symbolic-ref --short -q HEAD` (rama "no nacida" antes del primer commit), `status --porcelain` (parseo estable cross-versiones), `log --oneline -n 8`.

Si cualquier llamada falla: `disponible=False`, resto en valor neutro. **La coordinación NO debe depender de que git esté instalado**.

## `commitear(mensaje, autor_nombre, autor_email)`

`git add -A` + `git commit` con identidad pasada inline (`-c user.name=... -c user.email=...`), no toca config global.

**El autor lo pone el SERVER**, no el cliente: no podés commitear como otro. Identidad derivada de `autor_git(usuario_autenticado)`.

Validación previa (BACKEND-AUDIT-0158):

- Mensaje no vacío, ≤8192 bytes.
- Sin `\x00` (corta argv en C).
- Nombre de autor: regex `[\w .'+,_-]+`, sin `\x00`/`\n`, ≤200 chars.
- Email: regex `[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+`.

**Chequeo "hay algo para commitear"**: con `status --porcelain`, no parseando el texto de `git commit` (cambia entre versiones/locale).

## `clonar(url, usuario, token)` (destructivo)

Reemplaza el workspace con `git clone <url>`. Las credenciales se pasan vía `GIT_ASKPASS` temporal (ver más abajo); NO van en argv ni en `origin`.

**Seguro-primero**: clona a un tmp, solo si SALE BIEN reemplaza el workspace actual.

```python
def clonar(self, url, usuario, token):
    if not _url_segura(url, permitir_local=True):
        return (False, "URL de repo no válida")
    
    tmp = Path(tempfile.mkdtemp(prefix="orux-clone-", dir=str(self._root.parent)))
    os.chmod(tmp, 0o700)
    destino = tmp / "repo"
    try:
        rc, out = self._git_cred(
            ["clone", "--no-hardlinks", "--", url, str(destino)],
            usuario, token, cwd=tmp,
        )
        if rc != 0:
            return (False, _detalle_remoto(out))
        # purga hooks heredados
        # reemplaza el contenido del workspace con el clon
        ...
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
```

Defensas:

- **Tmpdir bajo `_root.parent`** (no `/tmp`): mismo volumen ⇒ rename atómico; mismo dueño/permisos; otro proceso del host no puede leerlo (BACKEND-AUDIT-0154, -0155).
- **0700 al crear**: nadie más lo lee.
- **`--no-hardlinks`** (URL local): evita reusar `objects/` del host si el repo es local malformado (alternates apuntando afuera).
- **`--`** separator: la URL no se puede tratar como flag.
- **Purga `.git/hooks/`** post-clone: el repo remoto pudo traer hooks (`pre-commit`, `post-merge`) que correrían en el próximo `commit` con privilegios del server (BACKEND-AUDIT-0153).
- **Anti-traversal en el rename**: solo movemos hijos que `realpath(hijo)` queda dentro de `destino` real (symlinks que escapan se descartan, BACKEND-AUDIT-0157).
- **Sin `--depth=1`**: shallow clone rompe `push --force-with-lease` (historia incompleta). Para acotar tamaño usamos el timeout, no el shallow.

## `push(usuario, token, url?, rama?)`

Empuja a la rama especificada (default `HEAD`). **No fuerza, no fusiona**.

Si el remoto avanzó (non-fast-forward): rechaza con `(False, "el remoto cambió: hay que traer cambios (pull) antes de pushear — no implementado aún")`. **Honesto**: no fingimos que anda. A `main` o ramas compartidas NUNCA pisamos historia.

## `push_a_rama(usuario, token, rama, url?)` (capa 21)

Empuja a `refs/heads/<rama>` con `--force-with-lease` (la rama de publicación del equipo, p.ej. `orux/<team_id>`).

**Rama de publicación**: orux es su único escritor; los humanos integran vía PR DESDE ella en GitHub. La tesis "integración, no reemplazo".

- Antes del push: `git fetch origin <rama>` (best-effort) — siembra el remote-tracking para que el lease tenga base.
- `--force-with-lease`: si alguien más commiteó a mano esa rama, el lease RECHAZA y se dice claro:

```
"alguien commiteó a mano en «<rama>»: esa rama es de publicación,
no se commitea ahí — se abre PR desde ella"
```

Devuelve también el `pr_url` (de `_url_pr(remote_url, rama)`): URL de "abrir PR desde esta rama" en GitHub (parsea owner/repo de la URL del remote).

## Endurecimiento del subprocess git

### Allowlist de transportes

```python
_GIT_ENV_SEGURO = {
    "GIT_TERMINAL_PROMPT": "0",                  # nunca prompt interactivo
    "GIT_ALLOW_PROTOCOL": "file:git:http:https:ssh:ftp:ftps",
    "GIT_PROTOCOL_FROM_USER": "0",
}
_GIT_CONF_SEGURO = [
    "-c", "protocol.ext.allow=never",            # niega ext:: explícito
    "-c", "protocol.fd.allow=never",             # niega fd:: explícito
    "-c", "core.hooksPath=/dev/null",            # apaga hooks
]
```

`ext::sh -c "..."` haría ejecutar comandos arbitrarios en el server. La allowlist es la defensa real (CVE-2017-1000117 y familia).

### Env filtrado (allowlist)

```python
_ENV_ALLOWLIST = {
    "PATH", "HOME", "USER", "LOGNAME", "TMPDIR",
    "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES",
    "SSH_AUTH_SOCK", "SSH_AGENT_PID",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
}
```

Solo estas + `GIT_*` se pasan al subprocess. Sin esto, un hook leakeado del repo clonado podría exfiltrar `ORUX_*` / `STRIPE_*` / DB DSN con `env > log` (BACKEND-AUDIT-0152).

### Allowlist positiva de URL schemes

```python
_URL_HTTPS = re.compile(r"^https?://[A-Za-z0-9._:-]+(/[^\s]*)?$")
_URL_GIT = re.compile(r"^git://[A-Za-z0-9._:-]+(/[^\s]*)?$")
_URL_SSH = re.compile(r"^ssh://(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9._:-]+(/[^\s]*)?$")
_URL_SCP = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._-]*@[A-Za-z0-9._-]+:[A-Za-z0-9._/-]+$")
_URL_LOCAL = re.compile(r"^(?:file://)?(/|\./)[A-Za-z0-9._/-]+$")
```

Antes era denylist (`ext::`/`fd::`) — dependía de que el git del host estuviera parcheado. Con allowlist positiva (BACKEND-AUDIT-0156): si no matchea uno de los 5 regex, se rechaza.

Casos:

- HTTPS / HTTP estricto (no acepta opciones como user).
- `git://` (sin SSH).
- `ssh://` con user opcional.
- SCP-like `user@host:owner/repo` con user/host estrictos (CVE-2017-1000117 funcionaba porque git aceptaba `-oProxyCommand` como user).
- Local `(/...)` o `file:///...` — anti-traversal: rechaza CUALQUIER `..` en la URL.

`clonar` acepta local (`permitir_local=True`); `push` y `push_a_rama` no lo aceptan (`permitir_local=False`).

### Validación del nombre de rama

```python
_RAMA_OK = re.compile(r"^[A-Za-z0-9._/-]+$")

def _rama_segura(rama):
    return (
        bool(r)
        and not r.startswith("-")
        and ".." not in r
        and bool(_RAMA_OK.match(r))
    )
```

Sin esto, un `rama` con `..` o caracteres raros crea refs inesperados en el remoto. Un `rama` empezando con `-` se leería como opción de git.

### Credenciales efímeras vía `GIT_ASKPASS`

El secreto va SOLO en el env del subprocess, NO en argv (`ps` lo vería), NO en URL (`.git/config` lo guarda), NO en `credential.helper` (no cachea).

```python
_ASKPASS = (
    "#!/bin/sh\n"
    'case "$1" in\n'
    '  *[Uu]sername*) printf "%s" "$ORUX_GIT_USER" ;;\n'
    '  *) printf "%s" "$ORUX_GIT_TOKEN" ;;\n'
    "esac\n"
)
```

El script NO contiene el secreto — lo lee del env. Se crea en un dir 0700 con nombre único `orux-askpass-<pid>-<uuid>`, permisos 0700; se borra al terminar (en `finally`).

`git -c "credential.helper="` (vacío) además fuerza a git a NO cachear credenciales.

### Scrubbing de la salida

```python
def _scrubear(texto, token=None):
    if token and len(token) >= 8:
        out = out.replace(token, "***")
    out = _URL_CON_CRED.sub(r"\1\2:***@", out)  # https://user:token@host → ***
    return out
```

Cualquier mensaje que el caller (cliente o log) reciba está scrubeado. Defensa en profundidad: el token literal ya se reemplaza; URLs con cred embebidas (que git imprime en algunos errores) también.

**No scrubeamos "tokens-like"** (regex aleatorias largas): rompía paths de pytest legítimos y mensajes de error del usuario. Solo lo literal + URLs con cred.

### Timeouts separados

```python
_GIT_TIMEOUT_LOCAL = clamp(_env_int("ORUX_GIT_TIMEOUT_LOCAL", 10), min=5)
_GIT_TIMEOUT_REMOTO = clamp(_env_int("ORUX_GIT_TIMEOUT", 120), min=5)
_OPS_REMOTAS = {"fetch", "clone", "push", "pull", "ls-remote"}
```

`status`/`log`/`add`/`commit` son <1s; no hace falta esperarlas 2 minutos (BACKEND-AUDIT-0159). Sin separar, un `status` colgado bloqueaba el threadpool por el timeout remoto.

Clamp ≥5s para que `ORUX_GIT_TIMEOUT=0`/`-1` no rompan (BACKEND-AUDIT-0263).

### Cleanup de `/tmp/orux-clone-*` huérfanos

Proceso muerto a mitad de clone deja basura en `/tmp`. Un scan al import del módulo (best-effort) borra los `orux-clone-*` con `mtime` >24h y proceso no vivo (BACKEND-AUDIT-0229).

## Lección de diseño

Cuando algo es **vulnerable por construcción** (URL del cliente, token del cliente, repo arbitrario), las defensas se acumulan:

1. **Validar la entrada** (URL allowlist, rama allowlist).
2. **Restringir las capacidades** (`GIT_ALLOW_PROTOCOL`, `core.hooksPath`).
3. **Aislar el subprocess** (env allowlist, sin shell, argv directo).
4. **Manejar el secreto fuera de banda** (askpass temporal).
5. **Defensa en profundidad** (scrubbing, anti-traversal en rename).

Ninguna de estas defensas sola es suficiente. La combinación es lo que hace seguro al producto.

Ver también [`security/git.md`](../security/git.md).
