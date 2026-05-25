# Flow: Integración con Git

El workspace de cada equipo es un repo git real. Orux integra con git (no lo reemplaza). Lo que hace:

- **Lee estado** (rama, cambios sin commitear, últimos commits) y lo muestra al equipo.
- **Permite commit** desde el IDE (con autor del usuario autenticado).
- **Permite clone** (destructivo: reemplaza el workspace).
- **Permite push** a la rama del equipo (con `--force-with-lease` y link de PR) o a otra rama (sin forzar).

**No hace**: pull, fetch user-triggered, merge, resolución de conflictos. Por tesis: prevenir colisiones con coordinación, no fusionar después.

## Estado del repo

Cada vez que un cliente entra al equipo, recibe en el handshake:

```python
GitStatusMessage{
    disponible: bool,         # False si git falló (no instalado, permisos, etc.)
    rama: str,                # "main", "feature/x", o "" si rama no-nacida
    cambios: int,             # archivos sin commitear (incluye sin trackear)
    commits: list[str],       # últimos 8: "abc1234 mensaje"
}
```

Cada cliente puede pedir refresh con `GitRefreshMessage` (sin payload). El server responde solo al solicitante (no broadcast — es info por-cliente).

Tras `Commit`, `Push`, `Clone`: el server difunde `GitStatusMessage` a TODOS (cambió el estado del repo, todos deben actualizar su UI).

## Flow: Commit desde el IDE

```
Ana                  Server                 GitPort                 Workspace
───                  ──────                 ───────                 ─────────
  │── Commit ─────────→│                       │                        │
  │   {message: "..."} │                       │                        │
  │                    │ autor = autor_git(ana_username)                │
  │                    │   → ("ana", "ana@orux.local")                  │
  │                    │                       │                        │
  │                    │ async with rt._git_lock:                       │
  │                    │  to_thread:                                    │
  │                    │   git.commitear(msg, "ana", "ana@orux.local") │
  │                    │     → git add -A                              │
  │                    │     → git -c user.name=ana -c user.email=...  │
  │                    │       commit -m "msg"                          │
  │                    │← (ok, "commit creado")                         │
  │                    │                       │                        │
  │←── GitResult ──────│                       │                        │
  │   {ok: true, ...}  │                       │                        │
  │                    │                                                │
  │←── GitStatus ──────────────→ (a todos)                              │
  │   {cambios: 0, rama: ..., commits: ["abc... msg", ...]}             │
```

### Autor

El autor lo pone el server desde la identidad autenticada (capa 7), NO el cliente: **no podés commitear como otro**. `autor_git(usuario)` deriva nombre + email:

```python
def autor_git(usuario):
    if "@" in usuario:
        return usuario.split("@", 1)[0], usuario  # email real
    return usuario, f"{usuario}@orux.local"       # sintético
```

Email sintético `usuario@orux.local` — git exige un email; no tenemos uno real y no lo inventamos bonito a propósito (es honesto que sea sintético).

### Identidad inline

```bash
git -c user.name="ana" -c user.email="ana@orux.local" commit -m "..."
```

Pasada con `-c` para NO tocar `git config global`. La identidad de commit del runtime del equipo no contamina otras configuraciones del host.

### Validación del mensaje (BACKEND-AUDIT-0158)

- No vacío.
- ≤ 8192 bytes (sin esto un commit puede traer 8MB que git acepta sin chistar).
- Sin `\x00` (corta argv en C).
- Autor: regex `[\w .'+,_-]+`, sin `\x00`/`\n`, ≤200 chars.
- Email: regex válido.

### Chequeo "hay algo para commitear"

Con `git status --porcelain` (estable cross-versiones/locale). Si no hay cambios → `(False, "no hay cambios para commitear")`. No se intenta commit vacío.

## Flow: Clone (destructivo)

REEMPLAZA el workspace del equipo entero. Audit log obligatorio.

```
Ana (admin)              Server                              GitPort
─────────                ──────                              ───────
  │                          │                                  │
  │── Clone ────────────────→│                                  │
  │   {url, usuario, token}  │                                  │
  │                          │ logger.info("clone DESTRUCTIVO...")│
  │                          │                                  │
  │                          │ async with rt._git_lock:         │
  │                          │  to_thread:                      │
  │                          │   git.clonar(url, user, token)  │
  │                          │     → _url_segura(url) ✓        │
  │                          │     → mkdtemp(prefix=orux-clone-,│
  │                          │             dir=root.parent)    │
  │                          │     → chmod 0o700                │
  │                          │     → git -c core.hooksPath=/dev/null \
  │                          │           clone --no-hardlinks   \
  │                          │           -- <url> /tmp/repo     │
  │                          │     (con GIT_ASKPASS para token) │
  │                          │     → purgar .git/hooks          │
  │                          │     → reemplazar root con /tmp/repo
  │                          │     → cleanup /tmp/orux-clone-*  │
  │                          │← (ok, "repo clonado")            │
  │                          │                                  │
  │                          │  if ok:                          │
  │                          │   async with rt._estado_lock:    │
  │                          │     _reiniciar_para_todos(rt)    │
  │                          │     # workspace.recargar()       │
  │                          │     # ownership.reset()          │
  │                          │     # proposals.borrar_todo()    │
  │                          │     # reciclar_lsp()             │
  │                          │     # broadcast Init/Welcome/Ownership a todos
  │                          │                                  │
  │←── GitResult ──────────────                                  │
  │   {ok: true, ...}                                            │
  │                                                              │
  │←── Init/Welcome/Ownership ─────────→ (a TODOS los clientes del equipo)
  │   (refresh completo del workspace)                          │
```

### Coreografía del lock

`_h_clone` toma `rt._git_lock` (git serializado por equipo) Y `rt._estado_lock` (reinicio del estado).

**Orden importante**: git_lock → estado_lock (anidados). Otros handlers solo toman estado_lock o git_lock por separado. Sin un orden consistente, dos handlers en orden inverso se bloquean mutuamente (deadlock).

### Seguridad del clone

Ver [`adapters/git.md`](../adapters/git.md) y [`security/git.md`](../security/git.md) — el clone es la operación más expuesta (URL del cliente). Defensas:

- Allowlist de URL schemes (https/git/ssh/scp/local).
- Allowlist de transporte git (`GIT_ALLOW_PROTOCOL`).
- Hooks deshabilitados (`core.hooksPath=/dev/null`).
- Env filtrado (no exfiltración por hook leakeado).
- Credenciales por askpass temporal (no en argv, no en URL).
- Tmpdir 0700 hermano del workspace.
- Anti-traversal en el rename de archivos.
- Hooks purgados post-clone defensa en profundidad.

### Credenciales efímeras

El `token` del cliente:

- NO viaja en argv (`ps` lo vería).
- NO va en `origin` (`.git/config` lo guardaría).
- NO se cachea (`credential.helper=` vacío).
- Vive SOLO en el env del subprocess, pasado a un script askpass temporal (0700) que se borra en `finally`.

**Las credenciales son SIEMPRE efímeras**. Ni siquiera el server las recuerda entre operaciones.

## Flow: Push

Dos modos según la rama destino:

### Modo 1: Push a la rama del equipo (default)

```
Push{rama: ""}  o  Push{rama: "orux/<team_id>"}
```

El server resuelve la rama del equipo: `orux/<team_id>` (e.g. `orux/abc12345`). Estrategia:

```bash
git fetch origin orux/abc12345   # best-effort, siembra remote-tracking
git push --force-with-lease origin HEAD:refs/heads/orux/abc12345
```

`--force-with-lease`: la rama es de **publicación** — orux es su único escritor. Los humanos integran vía PR DESDE ella en GitHub. Si alguien commiteó a mano en `orux/<team_id>`, el lease rechaza:

```
"alguien commiteó a mano en «orux/<team_id>»: esa rama es de publicación,
no se commitea ahí — se abre PR desde ella"
```

**Devuelve `pr_url`**: URL de "abrir PR desde esta rama" en GitHub. `_url_pr(remote_url, rama)` parsea owner/repo del remote y arma:

```
https://github.com/<owner>/<repo>/pull/new/<rama>
```

GitHub redirige a la página de crear PR de esa rama.

### Modo 2: Push a otra rama (e.g. `main`)

```
Push{rama: "main"}
```

`git push origin HEAD:refs/heads/main` (sin `--force-with-lease`). Si el remoto avanzó (non-fast-forward) → rechaza con `(False, "el remoto cambió: hay que traer cambios (pull) antes de pushear — no implementado aún")`.

**Honesto**: no fingimos que anda. A ramas compartidas NUNCA pisamos historia.

## Tesis del producto: integración, no reemplazo

Orux NO compite con GitHub/GitLab. La integración con git es deliberadamente mínima:

- **Estado de solo lectura** (capa 8): pregunta a git en el momento, no replica el árbol.
- **Commit** (capa 9): pieza chica, autor del server.
- **Clone destructivo** (capa 10): el equipo arranca de un repo existente.
- **Push a rama de publicación** (capa 21): orux propone, el humano integra.

Lo que NO hacemos (decisión explícita):

- **Pull/Fetch**: el dev hace `git pull` en su terminal si quiere traer cambios del remoto.
- **Merge**: rompería la tesis ("prevenir, no fusionar").
- **Branch management completo**: hoy solo dos ramas posibles del push (rama del equipo o cualquier otra). No hay UI para crear/borrar/listar ramas.
- **Conflict resolution**: si el push falla por non-ff, el dev resuelve en terminal.

## Limitación conocida

Las **credenciales** son tomadas en cada operación remota desde el cliente. Si el usuario tiene 2FA en GitHub, necesita un Personal Access Token (no su password). No hay UX para "guardame estas credenciales para no preguntarlas cada vez" — por diseño, las credenciales son efímeras.

Mejora futura plausible: aceptar `git credential.helper` configurado en el servidor (con cuidado: vivimos en un contenedor multi-tenant).

## Diagnóstico

| Síntoma | Causa probable |
|---|---|
| `disponible: false` en GitStatus | `git` binario no instalado, o permisos rotos en `/data/ws/<team_id>` |
| `commits: []` con `disponible: true` | Rama no-nacida (no hay commits aún). Normal en repo recién creado |
| Commit `(False, "URL no válida")` | URL no pasa `_url_segura` (probablemente `ext::` o scheme raro) |
| Push `(False, "remoto cambió...")` | non-fast-forward sin force-with-lease (rama no es la del equipo) |
| Push `(False, "stale info / force-with-lease")` | Alguien commiteó a mano en la rama del equipo. La rama es de publicación |
| Push `(False, "usuario o token incorrectos")` | Credenciales rechazadas por GitHub. Token vencido / sin permisos |
| Logs `clone (DESTRUCTIVO) pedido por X` | Audit log; alguien hizo clone — verificar quién y por qué |

Ver [`adapters/git.md`](../adapters/git.md) para el detalle del adapter y [`security/git.md`](../security/git.md) para las defensas.
