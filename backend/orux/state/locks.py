"""Detección de qué líneas *destruye* una edición. Pieza pura de la capa 5.

La capa 5 previene la colisión: "nunca dos personas al mismo tiempo en la
misma línea". Para eso el servidor necesita saber, dado el contenido viejo y
el nuevo de un archivo, qué líneas del viejo está pisando el que edita.

La clave es usar un diff por **subsecuencia común más larga (LCS)**, no una
comparación posicional ingenua. Si alguien inserta una línea al principio,
una comparación posición-a-posición diría que *todas* las líneas siguientes
"cambiaron" — y bloquearíamos a gente que ni siquiera fue tocada. Con LCS,
insertar una línea es un solo "add" y las demás siguen "iguales": solo
contamos como tocadas las líneas viejas que de verdad se borran o se
modifican. Insertar texto nuevo no destruye la línea de nadie.

Esto es exactamente el mismo algoritmo que el diff del cliente (capa 4), pero
del lado servidor y respondiendo otra pregunta: no "qué mostrar", sino "qué
números de línea del contenido viejo desaparecen o cambian".
"""

from __future__ import annotations

from array import array

# Tope del producto n·m de la matriz LCS. Sin esto, un update con un archivo
# enorme (100k líneas vs 100k) aloca ~10^10 celdas y CONGELA el event loop
# para TODOS los equipos (esta función es síncrona en el hot path de
# UpdateMessage, no va a un hilo). Por encima del tope se degrada a una
# comparación posicional O(n): es CONSERVADORA (nunca reporta de menos), así
# que la capa 5 sigue protegiendo — solo es más estricta de lo necesario en
# un archivo gigantesco, caso que no es el de edición humana normal.
#
# Tope reducido (BACKEND-AUDIT-0082 / -0083): 1M celdas mantiene la latencia
# aceptable en el event loop (LCS de 1000x1000 son ~3MB de buffer con array
# de ints, milisegundos). Más allá: fallback posicional. La función ya es
# pura; el caller (`_aplicar` con `rt._estado_lock`) puede moverla a un
# `asyncio.to_thread` si quiere paralelizar; cambiarlo aquí rompería el
# orden de propuestas vs updates (decisión consciente: no se mueve).
_LCS_MAX_CELDAS = 1_000_000


def _tocadas_posicional(a: list[str], b: list[str]) -> set[int]:
    """Fallback O(n) para archivos patológicos: una línea vieja está 'tocada'
    salvo que sobreviva IDÉNTICA en su misma posición. Sobre-reporta cuando
    hubo inserciones (todo lo de abajo se ve desplazado), nunca sub-reporta:
    seguro para la capa 5 a cambio de ser conservador en el caso extremo."""
    tocadas: set[int] = set()
    for i, linea in enumerate(a):
        if i >= len(b) or b[i] != linea:
            tocadas.add(i + 1)
    return tocadas


def lineas_tocadas(viejo: str, nuevo: str) -> set[int]:
    """Números de línea (1-indexados) del `viejo` que `nuevo` borra o modifica.

    Una línea que solo se desplazó (porque se insertó otra arriba) NO está
    tocada: su texto sigue existiendo intacto en `nuevo`. Solo cuentan las
    líneas viejas que no sobreviven tal cual.
    """
    a = viejo.split("\n")
    b = nuevo.split("\n")
    n, m = len(a), len(b)

    if n * m > _LCS_MAX_CELDAS:
        # Archivo gigante: la matriz LCS mataría el server. Degradar.
        return _tocadas_posicional(a, b)

    # LCS por programación dinámica con `array.array('i')` plano: 1 buffer
    # de (n+1)*(m+1) ints en vez de N+1 listas Python (BACKEND-AUDIT-0083:
    # ~28 bytes/PyObject vs 4 bytes/int = ~7x menos memoria + cache-friendly).
    cols = m + 1
    lcs = array("i", [0] * ((n + 1) * cols))
    for i in range(n - 1, -1, -1):
        base_i = i * cols
        base_i1 = (i + 1) * cols
        ai = a[i]
        for j in range(m - 1, -1, -1):
            if ai == b[j]:
                lcs[base_i + j] = lcs[base_i1 + j + 1] + 1
            else:
                d = lcs[base_i1 + j]
                r = lcs[base_i + j + 1]
                lcs[base_i + j] = d if d >= r else r

    tocadas: set[int] = set()
    i = j = 0
    while i < n and j < m:
        if a[i] == b[j]:
            # Línea vieja que sobrevive idéntica: NO tocada.
            i += 1
            j += 1
        elif lcs[(i + 1) * cols + j] >= lcs[i * cols + j + 1]:
            # a[i] no está en la subsecuencia común: se borró/modificó.
            tocadas.add(i + 1)  # 1-indexado, como las líneas de presencia
            i += 1
        else:
            # b[j] es una inserción: no destruye ninguna línea vieja.
            j += 1
    # Lo que quede de `a` sin emparejar también son líneas viejas que mueren.
    while i < n:
        tocadas.add(i + 1)
        i += 1
    return tocadas
