"""Workspace: el conjunto de archivos que el equipo está editando.

Antes (capa cero) teníamos un solo `Document` en el servidor. Ahora tenemos un
**workspace**, que es un mapa de `path -> Document`. Cada archivo vive como un
Document independiente, lo cual es importante: significa que cuando llegue el
momento de ediciones concurrentes con CRDT, cada archivo es su propio "espacio"
de sincronización y los cambios en `main.py` no compiten con cambios en `auth.py`.

Esa decisión se siente trivial ahora pero es load-bearing: toda la arquitectura
posterior (ownership por archivo, presencia por archivo, análisis semántico que
detecta usos cruzados entre archivos) asume que el archivo es la unidad mínima
de coordinación.

Límites (BACKEND-AUDIT-0070): topes blandos por workspace, validados en el
update. Sin esto un cliente puede llenar el workspace de N archivos hasta OOM.
- `MAX_ARCHIVOS`: 50_000 (un monorepo grande va por debajo).
- `MAX_BYTES_TOTAL`: 256MB (lo que cabe cómodo en memoria por equipo).
- `MAX_BYTES_ARCHIVO`: 1MB (alineado con `protocol.MAX_FRAME_BYTES`).

Cuando se rebasa, `update` rechaza con `WorkspaceLleno` y NO toca memoria/disco;
el server lo propaga al cliente como mensaje de error (igual que `decode`).
"""

from __future__ import annotations

import logging

from typing import TYPE_CHECKING

from ..._env import _env_int
from .document import Document

if TYPE_CHECKING:
    from ...ports import WorkspaceStoragePort

logger = logging.getLogger(__name__)

# Topes blandos (BACKEND-AUDIT-0070). Configurables vía env por si un
# operador legítimo necesita más holgura; defaults seguros.


MAX_ARCHIVOS = _env_int("ORUX_WS_MAX_ARCHIVOS", 50_000, 100, 1_000_000)
MAX_BYTES_ARCHIVO = _env_int(
    "ORUX_WS_MAX_BYTES_ARCHIVO", 1024 * 1024, 1024, 16 * 1024 * 1024,
)
MAX_BYTES_TOTAL = _env_int(
    "ORUX_WS_MAX_BYTES_TOTAL", 256 * 1024 * 1024, 1024 * 1024, 4 * 1024 * 1024 * 1024,
)


class WorkspaceLleno(ValueError):
    """El update excedería los topes del workspace. El caller lo trata como
    un mensaje malo y opcionalmente avisa al cliente."""


class Workspace:
    def __init__(self, storage: "WorkspaceStoragePort | None" = None) -> None:
        # Diccionario interno: path (string) -> Document. Es la fuente de verdad
        # del servidor sobre qué archivos existen y qué contienen.
        self._documents: dict[str, Document] = {}
        # Persistencia opcional (capa 3). Si es None, el workspace es puramente
        # en memoria — exactamente el comportamiento de capas 1 y 2, y lo que
        # usan los tests para arrancar siempre desde cero. Si hay storage, cada
        # update se escribe a disco y el estado sobrevive a reiniciar el server.
        # La memoria sigue siendo la fuente de verdad en caliente; el disco es
        # su respaldo, no un intermediario en el hot path de retransmisión.
        self._storage = storage

    def snapshot(self) -> dict[str, str]:
        """Foto del workspace completo: path -> contenido.

        Esto es lo que el servidor manda en el InitMessage a un cliente que
        acaba de conectarse. La copia es plana (no expone los objetos Document
        internos) porque el cliente no necesita saber sobre Document — solo
        necesita el texto.
        """
        return {path: doc.content for path, doc in self._documents.items()}

    def exists(self, path: str) -> bool:
        """¿El workspace ya conoce este path? Sirve para distinguir crear de editar.

        El protocolo no tiene un mensaje "crear archivo" (un update sobre un
        path nuevo lo crea). Pero el servidor sí necesita saber si un update es
        la *primera vez* que se ve un path, para, por ejemplo, hacer dueño a
        quien lo crea (capa 4). Por eso esta consulta es pública y explícita en
        vez de espiar el dict interno desde afuera.
        """
        return path in self._documents

    def get_or_create(self, path: str) -> Document:
        """Devuelve el Document de un path, creándolo vacío si no existe.

        Esta es la pieza que implementa "los archivos se crean al primer update".
        Decisión a futuro: si quieres que crear archivo sea explícito (botón
        "+ nuevo"), el cliente igualmente puede mandar un UpdateMessage con
        contenido vacío y este método lo crea sin distinción. Sirve para ambos
        casos sin lógica extra.
        """
        if path not in self._documents:
            self._documents[path] = Document()
        return self._documents[path]

    def update(self, path: str, content: str) -> None:
        """Aplica un cambio: 'el archivo en `path` ahora contiene `content`'.

        Crea el archivo si no existía. Cuando llegue el CRDT real, este método
        es donde la operación se aplicará al estado del archivo (no como
        sobrescritura completa sino como una operación incremental).

        Orden importante: PRIMERO memoria, DESPUÉS disco. Si persistir falla
        (path inseguro mandado por un cliente, disco lleno, permisos), la
        memoria ya quedó coherente y la retransmisión a los demás clientes
        sigue funcionando. Persistir nunca debe poder tumbar el tiempo real:
        por eso atrapamos y logueamos en vez de propagar.

        Topes (BACKEND-AUDIT-0070): si el update rompería los límites del
        workspace, levanta `WorkspaceLleno`. El bytes de `content` se compara
        en utf-8; si la cuenta total + el delta excede `MAX_BYTES_TOTAL` o el
        archivo solo excede `MAX_BYTES_ARCHIVO` o el conteo de archivos
        excede `MAX_ARCHIVOS`, se rechaza.
        """
        if len(content) > MAX_BYTES_ARCHIVO:
            raise WorkspaceLleno(
                f"archivo demasiado grande ({len(content)} > {MAX_BYTES_ARCHIVO})"
            )
        existente = self._documents.get(path)
        if existente is None and len(self._documents) >= MAX_ARCHIVOS:
            raise WorkspaceLleno(
                f"workspace al tope de archivos (>{MAX_ARCHIVOS})"
            )
        # Estimación de bytes totales: el contenido entrante reemplaza el
        # anterior. Es un cálculo barato sobre `len(content)` (UTF-16 internal
        # en Python; aproximación suficiente para una guarda).
        anterior_bytes = len(existente.content) if existente is not None else 0
        delta = len(content) - anterior_bytes
        if delta > 0:
            total = sum(len(d.content) for d in self._documents.values())
            if total + delta > MAX_BYTES_TOTAL:
                raise WorkspaceLleno(
                    f"workspace al tope de bytes ({total + delta} > {MAX_BYTES_TOTAL})"
                )
        self.get_or_create(path).update(content)
        if self._storage is not None:
            try:
                self._storage.guardar(path, content)
            except Exception:
                logger.exception("no se pudo persistir %r (sigo en memoria)", path)

    def delete(self, path: str) -> bool:
        """Borra un archivo del workspace (memoria + disco). Devuelve si existía.

        Mismo orden y misma resiliencia que `update`: primero memoria, después
        disco; si borrar del disco falla, la memoria ya quedó coherente y el
        tiempo real sigue. Devuelve False si el path no existía (el servidor
        entonces no difunde nada — borrar algo inexistente es no-op).
        """
        if path not in self._documents:
            return False
        del self._documents[path]
        if self._storage is not None:
            try:
                self._storage.borrar(path)
            except Exception:
                logger.exception("no se pudo borrar en disco %r", path)
        return True

    def recargar(self) -> None:
        """Tira el estado en memoria y lo reconstruye desde disco.

        Para el clone destructivo (capa 10): el disco ya tiene el repo nuevo;
        esto vacía lo viejo en memoria y carga lo nuevo. `cargar_de_disco`
        solo agrega, por eso primero limpiamos.

        ATENCIÓN — invariante a respetar fuera de aquí (BACKEND-AUDIT-0068):
        este método cambia EL CONJUNTO DE PATHS del workspace. Por sí solo,
        deja inconsistente al resto del estado del equipo:
        - `Ownership` puede tener dueños de paths que ya no existen.
        - `Proposals` puede tener propuestas sobre paths que ya no existen.
        - `Roster` puede tener presencias en paths que ya no existen.
        El caller (SyncServer en clone destructivo) DEBE además llamar a
        `Ownership.reset()` + `Proposals` nuevo + re-init a todos los
        clientes (eso lo hace `_reiniciar_para_todos`). Sin esa coreografía,
        este método solo NO basta — por eso no la asume aquí: el contrato es
        explícito, el caller lo gestiona.
        """
        self._documents.clear()
        self.cargar_de_disco()

    def cargar_de_disco(self) -> None:
        """Reconstruye el workspace desde el storage. Se llama una vez, al arrancar.

        No re-persiste lo que lee (sería redundante: ya está en disco). Sin
        storage configurado no hace nada, así un `Workspace()` en memoria
        —el de los tests— se comporta igual que siempre.
        """
        if self._storage is None:
            return
        for path, content in self._storage.cargar().items():
            self._documents[path] = Document(content)
