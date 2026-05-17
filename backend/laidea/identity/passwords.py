"""Hashing de contraseñas. Pieza pura de la capa 7.

Sin dependencias: `hashlib.pbkdf2_hmac` está en la stdlib y es suficiente y
correcto para un prototipo (no es `bcrypt`/`argon2`, pero es PBKDF2 con sal
por usuario y muchas iteraciones — no texto plano, no hash desnudo). El día
que esto importe de verdad se cambia la función de derivación sin tocar el
resto: por eso el formato guarda el algoritmo y las iteraciones.

Nunca se guarda la contraseña: solo `sal` aleatoria por usuario y el hash
derivado. La verificación es en tiempo constante (`hmac.compare_digest`) para
no filtrar información por el tiempo de respuesta.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# Iteraciones de PBKDF2. Más = más caro de crackear y de verificar. Este valor
# es un punto razonable para prototipo; vive aquí, no esparcido, para subirlo
# en un solo lugar cuando haga falta.
_ITERACIONES = 240_000


def hash_password(password: str) -> str:
    """Deriva un registro verificable a partir de la contraseña.

    Devuelve un string `algoritmo$iteraciones$sal_hex$hash_hex`. Todo lo que
    el store necesita persistir va ahí: es autodescriptivo, así verificar no
    depende de constantes globales que pudieran cambiar.
    """
    if not password:
        raise ValueError("la contraseña no puede estar vacía")
    sal = secrets.token_bytes(16)
    derivado = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), sal, _ITERACIONES
    )
    return f"pbkdf2_sha256${_ITERACIONES}${sal.hex()}${derivado.hex()}"


def verificar_password(password: str, registro: str) -> bool:
    """¿`password` produce el `registro` guardado? Comparación en tiempo constante.

    Tolerante a registros corruptos/desconocidos: si el formato no cuadra,
    devuelve False en vez de explotar (un store manipulado no debe tumbar el
    login de todos).
    """
    try:
        algo, iteraciones, sal_hex, hash_hex = registro.split("$")
        if algo != "pbkdf2_sha256":
            return False
        derivado = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(sal_hex),
            int(iteraciones),
        )
        return hmac.compare_digest(derivado.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False
