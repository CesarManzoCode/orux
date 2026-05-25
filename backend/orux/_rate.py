"""Helper compartido de rate-limiting por ventana deslizante.

Antes había DOS copias del MISMO algoritmo, idénticas en lógica:
- `adapters/inbound/websocket/sync.py::SyncServer._throttle` (anti-abuso del
  register / login del WS),
- `adapters/inbound/http/app.py::_rate_limit + _purgar_buckets` (login del
  operador HTTP, /errors, /track).

Ambas implementan exactamente:

1. bucket por clave (IP) con timestamps `monotonic` en una lista,
2. limpieza perezosa del bucket en cada llamada (descarta los `> corte`),
3. GC perezoso del dict global con tope de 10_000 claves — descarta las
   que ya vencieron la ventana (no solo las vacías), porque un atacante
   rotando >10k claves con goteo las mantiene no-vacías y el dict crecería
   sin control,
4. True = permitido, False = bloqueado.

Centralizar acá vuelve cualquier ajuste de política (ventana, tope, GC) una
edición en UN solo lugar. La duplicidad era drift-prone: cambiar la ventana
en una copia y olvidar la otra no rompía tests.
"""

from __future__ import annotations

import time


# Tope por defecto de claves en el dict antes de disparar el GC perezoso.
# El factor 10_000 es lo que ambas copias usaban hardcodeado; lo mantenemos
# como default para que el comportamiento sea byte-equivalente.
TOPE_BUCKETS_DEFAULT = 10_000


def permitir_evento(
    buckets: dict[str, list[float]],
    clave: str,
    tope: int,
    ventana_seg: float,
    *,
    tope_buckets: int = TOPE_BUCKETS_DEFAULT,
) -> bool:
    """¿`clave` puede consumir un evento ahora? True = OK (registra el
    evento); False = ya superó `tope` eventos en `ventana_seg` segundos.

    Bucket por `clave` con limpieza perezosa por llamada. GC del dict
    global si supera `tope_buckets`: descarta claves cuya última muestra
    ya venció la ventana, no solo las vacías.

    La función NO toma locks: cada call-site es síncrono dentro de su
    propia corutina (CPython garantiza atomicidad de operaciones sobre
    dict/list sin `await` en medio). Si algún día se introduce un `await`
    acá adentro, hay que repensar concurrencia.
    """
    ahora = time.monotonic()
    corte = ahora - ventana_seg
    bucket = buckets.setdefault(clave, [])
    bucket[:] = [t for t in bucket if t > corte]
    if len(bucket) >= tope:
        return False
    bucket.append(ahora)
    if len(buckets) > tope_buckets:
        muertas = [
            k for k, v in buckets.items() if not v or v[-1] <= corte
        ]
        for k in muertas:
            buckets.pop(k, None)
    return True
