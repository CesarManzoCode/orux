"""Punto de entrada: `python -m orux.server` o `orux-server`.

Aquí —y solo aquí— se cablea la persistencia real (capa 3). El `SyncServer`
no sabe de directorios por sí mismo: recibe un `DiskStorage` inyectado. Eso
mantiene los tests arrancando en memoria y deja la decisión de "dónde se
guarda" en un único lugar visible.

**Por qué el directorio por defecto está FUERA del repo** (`~/.orux/...`):
desde capa 14 el frontend es React+Vite (un único contenedor multi-stage,
no se sirve más con Live Server desde dentro del repo). Mantener el estado
de runtime FUERA del árbol del repo sigue siendo correcto: evita que
herramientas locales (linters, formatters, watchers de IDE) crucen con el
workspace persistido, y la ruta es explícita para ops (`~/.orux/...`).
La nota histórica sobre Live Server quedó en `CLAUDE.md` (capa 14).

Cuando hay integración con Git, esta capa decide su propia ubicación
dentro del repo del usuario; ese es su problema, no el del runtime.

Se puede sobreescribir con la variable de entorno `ORUX_DATA`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from secrets import token_hex

from ..composition import AppConfig, build_server
from .sync import TeamRuntime  # re-export para compat con callers externos

# Compat: __main__ históricamente re-exportaba `SyncServer` para callers
# externos. Lo mantenemos por ahora.
from .sync import SyncServer  # noqa: F401

# Todo el estado de ejecución vive bajo ~/.orux, FUERA del árbol del
# proyecto a propósito (ver más abajo). El workspace en un subdir; usuarios,
# ownership y el secreto de firma como archivos hermanos.
BASE_POR_DEFECTO = Path.home() / ".orux"

logger = logging.getLogger(__name__)


def _secreto(base: Path) -> str:
    """Secreto para firmar tokens de sesión, estable entre reinicios.

    Prioridad: `ORUX_SESSION_SECRET` (env) > archivo `~/.orux/secret`.

    El env existe para GitHub OAuth: el callback corre en OTRO proceso (el
    contenedor `api`/Starlette) y tiene que firmar el token de sesión con el
    MISMO secreto que este server WS verifica. Compartir un archivo entre
    contenedores sería frágil; una variable de entorno inyectada a ambos es
    explícita y robusta. Sin el env se mantiene el comportamiento histórico
    (archivo): backward-compatible, y OAuth simplemente queda deshabilitado
    (cerrado por defecto), nunca a medias.

    El archivo se guarda en `~/.orux/secret` y se genera la primera vez.
    Estable = los tokens de sesión guardados en los clientes siguen valiendo
    tras reiniciar el server (no obliga a re-loguear a todos). Si alguien
    borra el archivo, simplemente todos re-loguean una vez.
    """
    env = os.environ.get("ORUX_SESSION_SECRET", "").strip()
    f = base / "secret"
    log = logger
    if env and f.exists():
        try:
            del_archivo = f.read_text(encoding="utf-8").strip()
            if del_archivo and del_archivo != env:
                # BACKEND-AUDIT-0290: la divergencia env vs archivo invalida
                # TODOS los tokens vivos (cada uno firmó con uno distinto).
                # Loguear ALTO para que se note en ops.
                log.warning(
                    "ORUX_SESSION_SECRET difiere del archivo %s: los tokens "
                    "firmados antes de este boot dejaron de valer", f,
                )
        except OSError as e:
            # Antes era `pass` silencioso: si el archivo existe pero no se
            # puede LEER (permisos rotos en /data, FS sin permiso), perdíamos
            # la oportunidad de avisar la divergencia env vs archivo en este
            # boot. Logueamos warning explícito; el flujo sigue (este branch
            # es solo para alertar, no obligatorio para arrancar).
            log.warning(
                "no se pudo leer %s para chequear divergencia env vs archivo: %s",
                f, e,
            )
    if env:
        return env
    if f.exists():
        try:
            return f.read_text(encoding="utf-8").strip()
        except OSError as e:
            # Existe pero no se puede leer (permisos): morir con un mensaje
            # accionable, no con un traceback crudo de bajo nivel.
            raise SystemExit(
                f"no se pudo leer el secreto de firma {f}: {e}"
            ) from e
    # Directorio 0700 también (BACKEND-AUDIT-0267): el archivo es 0600 pero
    # sin dir restrictivo otro usuario puede listarlo y ver QUE existe.
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(base, 0o700)
    except OSError as e:
        # El dir queda con el modo que dio mkdir (suele ser ok con umask
        # 077); el chmod era refuerzo defensivo. Antes era `pass` silencioso
        # — si el FS no soporta chmod (Windows, ciertos volúmenes Docker
        # mal montados), el operador NO se enteraba y el dir podía quedar
        # 0755. Warning explícito para que se note.
        log.warning(
            "no se pudo aplicar chmod 0700 a %s (el dir queda con su modo "
            "por defecto, revisá permisos): %s", base, e,
        )
    s = token_hex(32)
    # El secreto firma TODOS los tokens de sesión: quien lo lea forja la
    # sesión de cualquier usuario. Se crea 0600 de forma atómica (no
    # write_text+chmod, que deja una ventana world-readable).
    try:
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Race con otro proceso que también está arrancando (BACKEND-AUDIT-0287):
        # leemos lo que el ganador escribió en vez de explotar.
        return f.read_text(encoding="utf-8").strip()
    try:
        os.write(fd, s.encode("utf-8"))
    finally:
        os.close(fd)
    return s


async def _amain() -> None:
    log = logger
    env = os.environ.get("ORUX_DATA")
    base = Path(env) if env else BASE_POR_DEFECTO
    base.mkdir(parents=True, exist_ok=True)
    secret = _secreto(base)
    config = AppConfig.desde_env(base_dir=base, secret=secret)
    # Marca de versión + modo al inicio: sin esto, en logs de varios deploys
    # consecutivos es imposible saber qué binario emitió cada línea. La
    # version sale del env `ORUX_VERSION` (same que `/api/v1/status`); en dev
    # cae a "dev". `dsn` se anuncia presente/ausente, NUNCA el valor (trae
    # credenciales).
    log.info(
        "orux-server v%s arrancando (mode=%s, base=%s, host=%s:%d)",
        os.environ.get("ORUX_VERSION", "dev"),
        "postgres" if config.dsn else "json-dev",
        base, config.host, config.port,
    )
    # Composition root: arma el grafo cableado completo (Ports + adapters).
    # El __main__ solo gestiona señales y arranca el server.
    server = await build_server(config)
    host = config.host
    port = config.port
    # (antes había un `del log` con comentario "mantener el binding" — la
    # acción contradecía al comentario y el `log.info(...)` del except de
    # más abajo levantaba NameError silencioso al recibir SIGTERM/SIGINT,
    # así que el shutdown limpio NUNCA dejaba rastro en los logs.)

    # SIGTERM/SIGINT: el server WS atiende ConnectionClosed por conexión,
    # pero el loop principal de `server.run` se cancelaría como traceback
    # crudo de KeyboardInterrupt. Registramos handlers que cancelan la
    # tarea principal limpiamente, así `asyncio.run` devuelve sin ruido y
    # las tareas de fondo (`barrer_*`) reciben CancelledError ordenada.
    # `add_signal_handler` requiere el loop corriendo: por eso va en
    # `_amain`, no en `main` (BACKEND-AUDIT-0293).
    tarea_principal = asyncio.create_task(server.run(host=host, port=port))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, tarea_principal.cancel)
        except NotImplementedError:
            # Windows / loops alternativos: el handler estándar de Python
            # sigue funcionando, solo perdemos el cierre 100% silencioso.
            pass
    try:
        await tarea_principal
    except asyncio.CancelledError:
        log.info("server: shutdown limpio por señal")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
