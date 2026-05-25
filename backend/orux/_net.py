"""Helpers de red defensivos compartidos.

Aislado acá (no en `_env.py`) porque son lógica de red, no de config.
Hoy hay un solo helper, `ip_proxy_confiable`, usado por la cáscara HTTP
de la API y por el server WS para decidir si confiar en cabeceras tipo
`X-Forwarded-For`.

BACKEND-AUDIT M-04: antes ambos call-sites tomaban el primer elemento de
`X-Forwarded-For` sin chequear DESDE DÓNDE venía la conexión. Si un
atacante alcanzaba el contenedor directamente (mal config, otro pod en la
misma red Docker, port forward olvidado), inyectaba XFF arbitrario y
rotaba la IP usada por el rate-limit. Ahora XFF solo se honra cuando la
conexión TCP viene de una IP privada / loopback (Caddy en la red de
compose), que es la condición real del deploy: Caddy es lo ÚNICO público,
el contenedor api/orux nunca recibe tráfico directo de internet.
"""

from __future__ import annotations

import ipaddress

# Rangos a CONFIAR como "proxy interno". Explícitos, no `addr.is_private`
# de la stdlib: ese flag incluye TEST-NET (203.0.113/24, 192.0.2/24,
# 198.51.100/24) y otros "reserved" que NO son redes internas reales, y
# un test de regresión nos lo recordaría con un AssertionError. Acá la
# lista cubre exactamente lo que un Docker compose / k8s típico usa:
#  - RFC 1918: 10/8, 172.16/12, 192.168/16 (incluye el bridge Docker por
#    defecto en 172.17.x, las user networks en 172.18-31, los pods k8s en
#    10.x, las LANs domésticas en 192.168.x).
#  - Loopback: 127/8, ::1 (mismo host, healthcheck, dev sin proxy).
#  - ULA IPv6: fc00::/7 (equivalente IPv6 de RFC 1918).
_RANGOS_CONFIABLES = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


def ip_proxy_confiable(ip: object) -> bool:
    """¿`ip` es la dirección de un proxy de confianza (red privada o
    loopback)? Devuelve False ante cualquier cosa que no sea una IP
    válida (None, "unknown", str raro). Nunca lanza.

    NO incluimos link-local (169.254/16, fe80::/10) ni rangos "reserved"
    que la stdlib clasifica como privados pero NO son redes internas
    reales (TEST-NET). Un atacante en la misma LAN del VPS no debería
    contar como "trusted proxy" — este deploy tiene UN único proxy bien
    identificado (Caddy en la red Docker compose).
    """
    if not isinstance(ip, str) or not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in red for red in _RANGOS_CONFIABLES)
