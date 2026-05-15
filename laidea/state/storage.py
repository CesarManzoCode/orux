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
from pathlib import Path

logger = logging.getLogger(__name__)


class DiskStorage:
    def __init__(self, root: Path | str) -> None:
        # `root` es la carpeta donde vive el workspace en disco. La guardamos
        # resuelta (absoluta, sin `..`) porque la usamos como frontera de
        # seguridad: todo lo que escribamos tiene que caer dentro de aquí.
        self.root = Path(root).resolve()

    def _destino(self, path: str) -> Path:
        """Traduce un `path` del protocolo a una ruta real en disco, segura.

        Es el único lugar donde un string que vino por la red se convierte en
        una ruta del filesystem. Por eso toda la validación vive aquí y no
        repartida: si algún día hay otra forma de escribir, pasa por acá.

        Rechaza con `ValueError`:
        - paths vacíos o que son el propio directorio raíz (no son un archivo);
        - cualquier path que, una vez resuelto, caiga fuera de `root` (absoluto
          como `/etc/passwd`, o con `..` que se escapa).
        """
        if not path or path in (".", "/"):
            raise ValueError(f"path inválido: {path!r}")
        # `root / path` con un path absoluto descarta root y queda absoluto;
        # con `..` sube de nivel. `resolve()` colapsa todo eso a una ruta real
        # que después comparamos contra root. Esta es la línea de defensa.
        destino = (self.root / path).resolve()
        if destino == self.root or not destino.is_relative_to(self.root):
            raise ValueError(f"path fuera del workspace: {path!r}")
        return destino

    def guardar(self, path: str, content: str) -> None:
        """Escribe el contenido de un archivo a disco, creando subcarpetas.

        Last-write-wins igual que en memoria: sobrescribe el archivo entero.
        Cuando llegue el CRDT, lo que se persista será el estado del CRDT, no
        un volcado de texto plano — pero esa decisión es de la capa 4.
        """
        destino = self._destino(path)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(content, encoding="utf-8")

    def cargar(self) -> dict[str, str]:
        """Lee todo el workspace de disco: `path -> contenido`.

        Es lo que el servidor usa al arrancar para reconstruir el estado. Si el
        directorio todavía no existe (primer arranque limpio), no es un error:
        simplemente no hay nada que cargar y devolvemos un dict vacío.

        Las claves se devuelven en formato POSIX (`src/auth.py`, con `/`)
        siempre, aunque el sistema use `\\`, porque ese es el formato que viaja
        por el protocolo y con el que el resto del sistema indexa el workspace.
        """
        if not self.root.exists():
            return {}
        archivos: dict[str, str] = {}
        for p in sorted(self.root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(self.root).as_posix()
            try:
                archivos[rel] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Un binario que alguien dejó en la carpeta. No es del workspace
                # de texto que manejamos hoy; lo saltamos en vez de explotar.
                logger.warning("archivo no es texto utf-8, se omite: %s", rel)
        return archivos
