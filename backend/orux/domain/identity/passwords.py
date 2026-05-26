"""Hashing de contraseñas. Pieza pura de la capa 7.

Sin dependencias: `hashlib.pbkdf2_hmac` está en la stdlib y es suficiente y
correcto para un prototipo (no es `bcrypt`/`argon2`, pero es PBKDF2 con sal
por usuario y muchas iteraciones — no texto plano, no hash desnudo). El día
que esto importe de verdad se cambia la función de derivación sin tocar el
resto: por eso el formato guarda el algoritmo y las iteraciones.

Nunca se guarda la contraseña: solo `sal` aleatoria por usuario y el hash
derivado. La verificación es en tiempo constante (`hmac.compare_digest`) para
no filtrar información por el tiempo de respuesta.

Hardening (auditoría):
- BACKEND-AUDIT-0005: tope mínimo y máximo de longitud. Sin máximo, un POST
  con 1MB de contraseña hace PBKDF2 trabajar sobre 1MB de input → DoS de CPU.
- BACKEND-AUDIT-0006: iteraciones a 600k (recomendación OWASP 2023+). El
  formato `pbkdf2_sha256$N$...` permite migrar hashes viejos en login: si
  el store tiene un registro con N<600k y la pwd verifica, el caller puede
  re-hashear con N=600k. Acá solo exponemos el helper `necesita_rehash`.
- BACKEND-AUDIT-0007: el marker externo se chequea en la PRIMERA línea, no
  depende de que el split por `$` produzca exactamente 1 elemento.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# Iteraciones de PBKDF2. OWASP (2023+) recomienda 600k para PBKDF2-SHA256;
# subimos desde 240k (BACKEND-AUDIT-0006). Login con re-hash transparente:
# `necesita_rehash(registro)` permite al caller actualizar el hash al verificar.
_ITERACIONES = 600_000

# Topes de longitud (BACKEND-AUDIT-0005). Mínimo razonable para una pwd; el
# máximo previene DoS de CPU: PBKDF2 procesa el input completo, así que una
# pwd de 1MB es 1MB * 600k iteraciones de SHA256 ≈ minutos de CPU. 128 es
# holgado para uso humano y barato para el server.
_PWD_MIN = 8
_PWD_MAX = 128

# Registro de contraseña de una cuenta SIN contraseña (identidad externa:
# OAuth). A propósito NO tiene el formato `algo$iter$sal$hash`, así que
# `verificar_password` cae en su rama tolerante y devuelve False SIEMPRE: a
# una cuenta de GitHub no se entra nunca por contraseña, solo por su
# proveedor. Es un valor, no un secreto.
MARCADOR_EXTERNO = "externo-oauth-sin-password"


def hash_password(password: str) -> str:
    """Deriva un registro verificable a partir de la contraseña.

    Devuelve un string `algoritmo$iteraciones$sal_hex$hash_hex`. Todo lo que
    el store necesita persistir va ahí: es autodescriptivo, así verificar no
    depende de constantes globales que pudieran cambiar.

    Rechaza pwd vacía, muy corta (<8) o muy larga (>128) con `ValueError`:
    el caller (UserStore.registrar / cambiar_password) lo propaga al cliente.
    """
    if not password:
        raise ValueError("la contraseña no puede estar vacía")
    if len(password) < _PWD_MIN:
        raise ValueError(f"la contraseña debe tener al menos {_PWD_MIN} caracteres")
    if len(password) > _PWD_MAX:
        raise ValueError(f"la contraseña no puede pasar de {_PWD_MAX} caracteres")
    sal = secrets.token_bytes(16)
    derivado = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), sal, _ITERACIONES
    )
    return f"pbkdf2_sha256${_ITERACIONES}${sal.hex()}${derivado.hex()}"


def verificar_password(password: str, registro: str) -> bool:
    """¿`password` produce el `registro` guardado? Comparación en tiempo constante.

    Tolerante a registros corruptos/desconocidos: si el formato no cuadra,
    devuelve False en vez de explotar (un store manipulado no debe tumbar el
    login de todos). Y el MARCADOR_EXTERNO se rechaza explícitamente antes
    de cualquier parsing (BACKEND-AUDIT-0007: defensa en profundidad si el
    formato del marker evoluciona).
    """
    if registro == MARCADOR_EXTERNO:
        return False
    # Antes de hacer PBKDF2 con la pwd entrante, descartamos pwds patológicas:
    # un atacante puede mandar 10MB en cada intento aunque el campo de pwd
    # del cliente tenga tope, si llega aquí por otra vía. Mismo límite que
    # `hash_password` (cap simétrico).
    if not isinstance(password, str) or len(password) > _PWD_MAX:
        return False
    try:
        algo, iteraciones, sal_hex, hash_hex = registro.split("$")
        if algo != "pbkdf2_sha256":
            return False
        # AUDITORIA-SEGURIDAD 2026-05-25 B-PERS-06: clamp de iteraciones
        # del registro. Si un atacante puede manipular el JSON/DB para
        # poner iteraciones=20_000_000 a un registro, cada `verificar`
        # ese usuario hace minutos de CPU (DoS de auth). El rango sano
        # cubre OWASP 2015 (100k) hasta OWASP 2030 (~2M).
        n_iter = int(iteraciones)
        if n_iter < 100_000 or n_iter > 2_000_000:
            return False
        derivado = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(sal_hex),
            n_iter,
        )
        return hmac.compare_digest(derivado.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def necesita_rehash(registro: str) -> bool:
    """¿El registro fue hecho con menos iteraciones que las actuales?

    True ⇒ el caller puede re-hashear silenciosamente al verificar OK. False
    si el formato no es pbkdf2_sha256 (marker externo, etc.) o ya está al día.
    """
    try:
        algo, iteraciones, _sal, _hash = registro.split("$")
        return algo == "pbkdf2_sha256" and int(iteraciones) < _ITERACIONES
    except (ValueError, AttributeError):
        return False
