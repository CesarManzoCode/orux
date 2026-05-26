"""Persistencia en disco: el workspace sobrevive a reiniciar el servidor.

Hasta la capa 2 todo el estado vivía solo en memoria del servidor. Reiniciar el
proceso (justo lo que pasa cada vez que cambiamos el protocolo) borraba todo el
workspace. Esta capa arregla exactamente ese dolor: al arrancar, el servidor
lee los archivos de un directorio en disco; cada edición se escribe ahí.

Decisiones de esta capa:

- **Mínima a propósito.** No hay historial, ni versiones, ni snapshots con
  fecha. Eso sería otra capa (y el CRDT real, capa 4, es quien va a necesitar
  guardar su propio estado interno). Aquí solo: `path -> archivo en disco`,
  last-write-wins, igual que la semántica que ya tenía el `Workspace`.

- **El directorio refleja el árbol real.** Un `path` como `src/auth.py` se
  guarda como `src/auth.py` con sus subcarpetas reales. Hoy ese directorio
  vive fuera del repo por una razón operativa (ver `server/__main__.py`: los
  watchers que recargan el navegador). Dónde debe vivir para que `git add`
  lo entienda es decisión de la futura capa de integración con Git, no de
  esta capa.

- **Los paths vienen del cliente, así que no son de confiar.** Un cliente
  (malicioso o con un bug) podría mandar `../../etc/passwd` o `/etc/shadow`.
  Validar que todo path resuelva DENTRO del directorio raíz no es paranoia
  prematura: es el mínimo necesario desde el momento en que el path cruza la
  red. Un path inseguro se rechaza con `ValueError`; quien llame decide qué
  hacer (el `Workspace` lo loguea y sigue, sin tumbar la conexión).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Tope por archivo al cargar de disco (BACKEND-AUDIT-0079): un PNG de 5GB
# en el workspace tirado por error reventaría el server al arrancar. 2MB
# es holgado para código (un .ts grande es <100KB, un .md grande es <500KB).
_MAX_BYTES_CARGAR = 2 * 1024 * 1024

# Tmp con pid: `.<digits>.tmp`. Sin esto, archivos legítimos `config.tmp`
# del repo del usuario se filtraban (BACKEND-AUDIT-0236).
_TMP_PID = re.compile(r"\.\d+\.tmp$")


class DiskStorage:
    def __init__(self, root: Path | str) -> None:
        # `root` es la carpeta donde vive el workspace en disco. La guardamos
        # resuelta (absoluta, sin `..`) porque la usamos como frontera de
        # seguridad: todo lo que escribamos tiene que caer dentro de aquí.
        self.root = Path(root).resolve()
        # Barrido perezoso de .tmp huérfanos al arrancar (BACKEND-AUDIT-0080):
        # SIGKILL entre write y replace deja `archivo.<pid>.tmp` sin pareja.
        # Si su pid no está vivo, lo limpiamos para no acumular basura.
        self._limpiar_tmps_huerfanos()

    def _limpiar_tmps_huerfanos(self) -> None:
        if not self.root.exists():
            return
        try:
            iterador = self.root.rglob("*.tmp")
        except OSError:
            return
        for p in iterador:
            try:
                if not p.is_file() or not _TMP_PID.search(p.name):
                    continue
                p.unlink()
            except OSError:
                pass

    def _destino(self, path: str) -> Path:
        """Traduce un `path` del protocolo a una ruta real en disco, segura.

        Es el único lugar donde un string que vino por la red se convierte en
        una ruta del filesystem. Por eso toda la validación vive aquí y no
        repartida: si algún día hay otra forma de escribir, pasa por acá.

        Rechaza con `ValueError`:
        - paths vacíos o que son el propio directorio raíz (no son un archivo);
        - cualquier path que, una vez resuelto, caiga fuera de `root` (absoluto
          como `/etc/passwd`, o con `..` que se escapa);
        - cualquier path donde un componente intermedio es un symlink que
          escapa de la raíz (BACKEND-AUDIT-0076: defensa contra symlinks
          ya plantados dentro del workspace que apuntan afuera).
        """
        if not path or path in (".", "/"):
            raise ValueError(f"path inválido: {path!r}")
        # `root / path` con un path absoluto descarta root y queda absoluto;
        # con `..` sube de nivel. `resolve()` colapsa todo eso a una ruta real
        # que después comparamos contra root. Esta es la línea de defensa.
        destino = (self.root / path).resolve()
        if destino == self.root or not destino.is_relative_to(self.root):
            raise ValueError(f"path fuera del workspace: {path!r}")
        # Anti-symlink intermedio: cualquier componente del path que SEA un
        # symlink y resuelva fuera de root es un escape (BACKEND-AUDIT-0076).
        actual = self.root
        for parte in destino.relative_to(self.root).parts:
            actual = actual / parte
            if actual.is_symlink():
                real = actual.resolve()
                if not real.is_relative_to(self.root):
                    raise ValueError(
                        f"path atraviesa un symlink fuera del workspace: {path!r}"
                    )
        return destino

    def guardar(self, path: str, content: str) -> None:
        """Escribe el contenido de un archivo a disco, creando subcarpetas.

        Last-write-wins igual que en memoria: sobrescribe el archivo entero.
        Cuando llegue el CRDT, lo que se persista será el estado del CRDT, no
        un volcado de texto plano — pero esa decisión es de la capa 4.

        Atómico (robustez B-varios): se escribe a un temporal en la MISMA
        carpeta y se hace `os.replace` (rename atómico en el mismo
        filesystem). Sin esto, un crash/disco-lleno a mitad de `write_text`
        deja el archivo del workspace TRUNCADO en disco; al reiniciar, ese
        archivo a medias se carga como la verdad y el dev pierde código en
        silencio. `ownership.json` ya se arregló así — este era el mismo
        agujero en el dato que más duele perder. El temporal lleva el pid
        para que dos escrituras del mismo path no pisen su propio temporal.
        """
        destino = self._destino(path)
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_name(f"{destino.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, destino)
        except Exception:
            # Si falló a mitad, no dejes el .tmp tirado contaminando el
            # workspace (se cargaría como un archivo más al reiniciar).
            tmp.unlink(missing_ok=True)
            raise

    def borrar(self, path: str) -> None:
        """Borra el archivo de disco. Valida el path igual que `guardar`.

        Si el archivo no existe en disco no es error (la memoria manda; el
        disco solo la sigue). `_destino` rechaza paths que se escapan, así un
        cliente no puede pedir borrar fuera del workspace.
        """
        destino = self._destino(path)
        destino.unlink(missing_ok=True)

    def cargar(self) -> dict[str, str]:
        """Lee todo el workspace de disco: `path -> contenido`.

        Es lo que el servidor usa al arrancar para reconstruir el estado. Si el
        directorio todavía no existe (primer arranque limpio), no es un error:
        simplemente no hay nada que cargar y devolvemos un dict vacío.

        Las claves se devuelven en formato POSIX (`src/auth.py`, con `/`)
        siempre, aunque el sistema use `\\`, porque ese es el formato que viaja
        por el protocolo y con el que el resto del sistema indexa el workspace.

        Hardening (auditoría):
        - PermissionError/OSError por archivo se loguea y se sigue, no se
          aborta toda la carga (BACKEND-AUDIT-0078). Un archivo con permisos
          raros no debe dejar el workspace VACÍO en memoria — el siguiente
          update lo pisaría todo.
        - Tope por archivo: 2MB. Un PNG/zip de GB no se carga (BACKEND-AUDIT-0079).
        - Filtro `.git` case-insensitive (BACKEND-AUDIT-0094): en HFS+/NTFS
          `.GIT/HEAD` debe filtrarse igual.
        - Filtro de `.tmp` solo cuando matchea `.<pid>.tmp` (BACKEND-AUDIT-0236):
          un `config.tmp` legítimo del repo se cargaba antes.
        """
        if not self.root.exists():
            return {}
        archivos: dict[str, str] = {}
        for p in self.root.rglob("*"):
            try:
                if not p.is_file():
                    continue
            except OSError:
                continue
            partes = p.relative_to(self.root).parts
            # El workspace puede SER un repo git (capa 8): `.git/` es interno
            # de git, no archivos del proyecto. Comparación case-insensitive
            # para FS case-insensitive (`.GIT/HEAD` ≡ `.git/HEAD`).
            if any(parte.lower() == ".git" for parte in partes):
                continue
            # Temporal de una escritura atómica que un crash duro (corte de
            # luz entre write_text y os.replace) dejó a medias: NO es un
            # archivo del proyecto. Solo filtramos los que matchean `.<pid>.tmp`
            # para no excluir archivos legítimos del repo del usuario.
            if _TMP_PID.search(p.name):
                continue
            # Tope de tamaño: archivos gigantes no entran a memoria. El
            # workspace de orux es código de texto, no binarios grandes.
            try:
                st = p.stat()
            except OSError as e:
                logger.warning("no se pudo statear %s: %s", p, e)
                continue
            if st.st_size > _MAX_BYTES_CARGAR:
                logger.warning(
                    "archivo demasiado grande, se omite: %s (%d bytes)",
                    p, st.st_size,
                )
                continue
            rel = p.relative_to(self.root).as_posix()
            # AUDITORIA-SEGURIDAD 2026-05-25 B-WS-09: aplicar `path_seguro`
            # al rel-path computado del FS. Si por algún ataque al disco
            # (symlink, FS case-sensitive raro) llegamos a un nombre que
            # no pasaría la frontera WS, lo saltamos en vez de inyectarlo
            # a memoria. Importación local para no acoplar con el módulo
            # principal de paths en este loop crítico.
            from .paths import path_seguro as _path_seguro
            if not _path_seguro(rel):
                logger.warning("path inseguro descartado al cargar: %r", rel)
                continue
            try:
                archivos[rel] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Un binario que alguien dejó en la carpeta. No es del workspace
                # de texto que manejamos hoy; lo saltamos en vez de explotar.
                logger.warning("archivo no es texto utf-8, se omite: %s", rel)
            except (PermissionError, OSError) as e:
                # Permisos raros o IO error: NO aborta la carga entera
                # (BACKEND-AUDIT-0078). Loguear y seguir.
                logger.warning("no se pudo leer %s: %s", rel, e)
        return archivos
