"""Validación de paths del protocolo — robustez (frontera del mensaje).

`DiskStorage._destino` ya rechaza paths peligrosos, pero SOLO en la frontera
del disco. La auditoría encontró el agujero: un cliente que manda
`update` con path `../x`, `/etc/passwd`, `""` o con un NUL mete ese path en
el estado EN MEMORIA (workspace/ownership/proposals) y el server lo difunde a
todo el equipo como archivo fantasma — aunque el disco lo bloquee después y
quede solo en RAM. El daño (basura difundida, ownership/propuestas sobre un
path imposible) ya ocurrió antes de tocar el disco.

La defensa correcta es validar el path al RECIBIR el mensaje, no solo al
escribir. Esta pieza es PURA (no toca disco, no necesita un root): decide si
un string es un path de proyecto plausible. Es deliberadamente conservadora —
ante la duda, inválido: un path raro rechazado es un archivo que el dev
vuelve a crear bien; uno aceptado es basura difundida a todo el equipo.

Reglas (todas necesarias, ninguna paranoia prematura — el path cruzó la red):

- string no vacío y de largo razonable (un path de KB es ataque/bug, no un
  archivo);
- sin bytes de control ni NUL (un `\\x00` parte rutas en C y miente al disco);
- relativo: ni `/raíz`, ni `C:\\`, ni `\\\\servidor` (UNC);
- POSIX: el protocolo viaja con `/`; un `\\` es evasión (`..\\..`) o ambigüedad
  — se rechaza de plano en vez de intentar normalizarlo;
- ningún segmento `.`, `..` ni vacío (`a//b`): el `..` es el clásico escape de
  directorio y el vacío es un path malformado.
"""

from __future__ import annotations

# Un path de proyecto real cabe de sobra acá; pasado esto es ataque o bug.
_MAX = 1024


def path_seguro(path: object) -> bool:
    """¿`path` es un path de proyecto plausible y NO peligroso?

    Devuelve un bool (nunca lanza): el llamador (server) trata False como
    "ignorá este mensaje y dejá rastro", igual que el resto de la robustez —
    un frame malo no tumba la conexión.
    """
    if not isinstance(path, str):
        return False
    if not path or len(path) > _MAX:
        return False
    # Bytes de control / NUL: `\x00` trunca rutas a nivel C y engaña al
    # chequeo de disco; \r\n\t en un path es siempre malformado.
    if any(ord(c) < 0x20 for c in path):
        return False
    # `\` = evasión o ambigüedad de plataforma. El protocolo es POSIX: no se
    # normaliza, se rechaza (normalizar es justo donde se cuelan los bypass).
    if "\\" in path:
        return False
    # Absolutos: raíz POSIX o unidad de Windows (`C:`). Un path de workspace
    # SIEMPRE es relativo a la raíz del equipo.
    if path.startswith("/"):
        return False
    if len(path) >= 2 and path[1] == ":":
        return False
    # Ningún segmento `.`/`..`/vacío. El `..` es el escape de directorio
    # clásico; el vacío (`a//b`, `a/`) es un path malformado.
    for seg in path.split("/"):
        if seg in ("", ".", ".."):
            return False
    return True
