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
  directorio y el vacío es un path malformado;
- caracteres que rompen URLs/git/shell/sistemas de archivos: `<`, `>`, `?`,
  `*`, `|`, `"` (Windows los prohíbe y git puede confundirse con `?`/`*`);
- caracteres de suplantación visual: zero-width y bidi-override (un atacante
  puede crear `auth.py` que se ve idéntico a otro pero está en una ruta
  distinta — fuente clásica de homograph attacks);
- segmentos con espacios al borde (`" a.py"`, `"a.py "`) — fuente típica de
  errores invisibles en checkouts/cli;
- profundidad y longitud por segmento acotadas (un path con 50 segmentos o
  un segmento de 500 caracteres no es código real);
- nombres reservados de Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9) — abrir
  uno en un checkout Windows reventaría la herramienta del dev.

Lo que NO hace (sigue siendo responsabilidad del backend):
- Resolver normalizaciones Unicode (NFC vs NFD): se compara byte-a-byte; si
  alguien manda `café` NFC y otro NFD, son paths distintos a propósito.
- Validar extensiones: el workspace acepta archivos arbitrarios (.md, .txt,
  .json, .yaml, ...). Eso lo gobierna la lista de tiers de análisis y el
  cliente con un mensaje claro, no `path_seguro`.
"""

from __future__ import annotations

# Topes más estrictos que antes (1024 era "para que no explote", no "lo que
# tiene sentido"): un path de 200 chars ya es un árbol profundo; un segmento
# de 80 chars es una clase larga; 16 niveles de carpeta es un monorepo. Si
# alguien hace algo más raro, casi seguro es bug o ataque.
_MAX = 200
_MAX_SEGMENTO = 80
_MAX_PROFUNDIDAD = 16

# Caracteres "ruidosos": rompen URLs, comandos shell, configs git, drivers
# de sistemas de archivos. Rechazamos en vez de "escapar" porque la app es
# multi-lenguaje y multi-OS; un path con `?` no aporta valor y rompe a algún
# dev del equipo en algún sistema.
_PROHIBIDOS = set('<>:"|?*')

# Suplantación visual (zero-width y bidi-override). Un `auth.py` con un
# `‮` invisible no se ve, pero ES otro archivo: el equipo está
# "editando" archivos distintos sin saberlo.
_INVISIBLES = {
    "​", "‌", "‍", "‎", "‏",  # ZWSP/ZWJ/etc.
    "‪", "‫", "‬", "‭", "‮",  # LRE/RLE/PDF/LRO/RLO
    "⁦", "⁧", "⁨", "⁩",            # LRI/RLI/FSI/PDI
    "﻿",                                            # BOM
}

# Nombres reservados de Windows (case-insensitive, sin importar extensión).
# Crear `CON.txt` en Windows no es un archivo: es el dispositivo de consola.
_RESERVADOS_WIN = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


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
    # Bytes de control / NUL / DEL: `\x00` trunca rutas a nivel C y engaña al
    # chequeo de disco; `\r\n\t` en un path es siempre malformado; `\x7f`
    # (DEL) cae fuera del rango imprimible normal.
    for c in path:
        co = ord(c)
        if co < 0x20 or co == 0x7F:
            return False
        if c in _PROHIBIDOS or c in _INVISIBLES:
            return False
    # `\` = evasión o ambigüedad de plataforma. El protocolo es POSIX: no se
    # normaliza, se rechaza (normalizar es justo donde se cuelan los bypass).
    if "\\" in path:
        return False
    # Absolutos: raíz POSIX o unidad de Windows (`C:`). Un path de workspace
    # SIEMPRE es relativo a la raíz del equipo. La regla "len>=2 and path[1]==':'"
    # de antes baneaba `a:b.py` legítimo; reemplazada por "letra + dos puntos"
    # estricto (drive de Windows: `C:` o `C:/`), que es la forma real del
    # absoluto Windows y deja pasar dos puntos en posiciones normales.
    if path.startswith("/"):
        return False
    if len(path) >= 2 and path[1] == ":" and path[0].isascii() and path[0].isalpha():
        return False
    # Segmentos: cada uno tiene reglas propias. Iteramos manual para dar
    # error temprano y barato.
    segs = path.split("/")
    if len(segs) > _MAX_PROFUNDIDAD:
        return False
    for seg in segs:
        if seg in ("", ".", ".."):
            return False
        if len(seg) > _MAX_SEGMENTO:
            return False
        # Espacios al borde del segmento: invisibles en logs, rompen
        # commands shell, fuente típica de bugs de "no se encuentra el
        # archivo" — rechazamos.
        if seg != seg.strip():
            return False
        # Nombres reservados Windows: el chequeo es por el "stem"
        # (lo de antes del último punto). `CON.txt` y `con` están vetados.
        stem = seg.rsplit(".", 1)[0] if "." in seg else seg
        if stem.upper() in _RESERVADOS_WIN:
            return False
    return True
