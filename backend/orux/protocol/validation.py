"""Validación defensiva del protocolo: topes de tamaño y lectores de campo.

Este módulo es una de las tres mitades del paquete `protocol` (ver
`messages.py` para las FORMAS y `codec.py` para encode/decode). Acá viven
SOLO las herramientas que verifican que un dato crudo del WebSocket respeta
el contrato — tipo, tamaño, presencia. `codec.decode` las usa para construir
cada mensaje sin tocar `data["x"]` desnudo (un acceso crudo truena con
`KeyError`; estos helpers levantan `ProtocolError` con un mensaje legible).

Se separó de `messages.py` porque no depende de ninguna dataclass: es lógica
pura de saneo, y aislarla deja que el archivo de formas quede sólo con formas.
"""

from __future__ import annotations

# Tope HARD del frame entero antes de decode (BACKEND-AUDIT-0033 / -0271). El
# server WS también pasa `max_size` a `serve(...)`; este es la defensa en el
# protocol module si llega a llamarse desde otro contexto. Subirlo aquí es
# rompedor (un commit con un patch gordo entra en updates).
MAX_FRAME_BYTES = 2 * 1024 * 1024  # 2 MB

# Topes por campo individual: cap simétrico entre lo que el server acepta y
# lo que un cliente legítimo podría mandar. Sin estos, un `content` de 1.9MB
# pasa el frame check y se procesa entero. Calibrados para casos legítimos:
# un archivo de 1MB es muy holgado (LSP/treesitter empieza a chillar antes).
_MAX_CONTENT = 1024 * 1024       # 1 MB
_MAX_MESSAGE = 8 * 1024          # 8 KB (commit message, reason, etc.)
_MAX_PATH = 1024                 # 1 KB (suficiente para nested dirs)
_MAX_USERNAME = 128
_MAX_PASSWORD = 256              # > passwords.py _PWD_MAX pero defensivo
_MAX_TOKEN = 4096                # tokens HMAC + base64 caben holgados
_MAX_URL = 2048
_MAX_LIST_ITEMS = 1024           # listas de strings (peers, symbols, etc.)
_MAX_STRING_FIELD = 1024         # campos cortos genéricos


class ProtocolError(ValueError):
    """Error de protocolo: el mensaje no respeta el contrato (forma, tamaño,
    tipo). Se sube como `ValueError` para que los catch del server existente
    sigan funcionando. Mensaje SIEMPRE legible para devolver al cliente."""


def _str(v: object, *, max_len: int = _MAX_STRING_FIELD,
         campo: str = "campo", permitir_vacio: bool = True) -> str:
    """Lee un campo string del dict, valida tipo y tope. Devuelve "" si falta
    o es None y `permitir_vacio` (default). Levanta `ProtocolError` con un
    mensaje legible si el tipo o el tamaño no cuadran."""
    if v is None:
        if permitir_vacio:
            return ""
        raise ProtocolError(f"falta '{campo}'")
    if not isinstance(v, str):
        raise ProtocolError(f"'{campo}' debe ser texto")
    if len(v) > max_len:
        raise ProtocolError(
            f"'{campo}' excede el tope ({len(v)} > {max_len} bytes)"
        )
    return v


def _int(v: object, *, default: int = 0, minimo: int | None = None,
         maximo: int | None = None, campo: str = "campo") -> int:
    """Lee un entero defensivamente. Acepta None (-> default), int real
    (no bool), o string convertible. Aplica clamp si min/max."""
    if v is None:
        return default
    if isinstance(v, bool):
        raise ProtocolError(f"'{campo}' debe ser entero, no bool")
    if isinstance(v, int):
        n = v
    elif isinstance(v, str):
        try:
            n = int(v)
        except ValueError:
            raise ProtocolError(f"'{campo}' debe ser entero") from None
    else:
        raise ProtocolError(f"'{campo}' debe ser entero")
    if minimo is not None and n < minimo:
        n = minimo
    if maximo is not None and n > maximo:
        n = maximo
    return n


def _bool(v: object, *, default: bool = False, campo: str = "campo") -> bool:
    """Lee un booleano. Estricto: solo True/False; un int=1 no cuenta para
    evitar confusiones de tipo."""
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    raise ProtocolError(f"'{campo}' debe ser true/false")


def _list_str(v: object, *, max_items: int = _MAX_LIST_ITEMS,
              max_len: int = _MAX_STRING_FIELD, campo: str = "campo") -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list):
        raise ProtocolError(f"'{campo}' debe ser lista")
    if len(v) > max_items:
        raise ProtocolError(f"'{campo}' excede {max_items} elementos")
    out: list[str] = []
    for it in v:
        if not isinstance(it, str):
            raise ProtocolError(f"elementos de '{campo}' deben ser texto")
        if len(it) > max_len:
            raise ProtocolError(f"un elemento de '{campo}' excede {max_len} bytes")
        out.append(it)
    return out


def _dict_str(v: object, *, max_items: int = 4096, max_key: int = _MAX_PATH,
              max_val: int = _MAX_CONTENT, campo: str = "campo") -> dict[str, str]:
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise ProtocolError(f"'{campo}' debe ser objeto")
    if len(v) > max_items:
        raise ProtocolError(f"'{campo}' excede {max_items} elementos")
    out: dict[str, str] = {}
    for k, val in v.items():
        if not isinstance(k, str) or not isinstance(val, str):
            raise ProtocolError(f"'{campo}' debe ser objeto texto->texto")
        if len(k) > max_key:
            raise ProtocolError(f"una clave de '{campo}' excede {max_key} bytes")
        if len(val) > max_val:
            raise ProtocolError(f"un valor de '{campo}' excede {max_val} bytes")
        out[k] = val
    return out
