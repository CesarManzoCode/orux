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


def lineas_tocadas(viejo: str, nuevo: str) -> set[int]:
    """Números de línea (1-indexados) del `viejo` que `nuevo` borra o modifica.

    Una línea que solo se desplazó (porque se insertó otra arriba) NO está
    tocada: su texto sigue existiendo intacto en `nuevo`. Solo cuentan las
    líneas viejas que no sobreviven tal cual.
    """
    a = viejo.split("\n")
    b = nuevo.split("\n")
    n, m = len(a), len(b)

    # LCS por programación dinámica: lcs[i][j] = largo de la subsecuencia
    # común más larga entre a[i:] y b[j:].
    lcs = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if a[i] == b[j]:
                lcs[i][j] = lcs[i + 1][j + 1] + 1
            else:
                lcs[i][j] = max(lcs[i + 1][j], lcs[i][j + 1])

    tocadas: set[int] = set()
    i = j = 0
    while i < n and j < m:
        if a[i] == b[j]:
            # Línea vieja que sobrevive idéntica: NO tocada.
            i += 1
            j += 1
        elif lcs[i + 1][j] >= lcs[i][j + 1]:
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
