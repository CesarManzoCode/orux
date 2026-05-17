"""API interna de operador (capa 23) — DESACOPLADA de todo.

Servicio HTTP propio (proceso/contenedor aparte), montado en `/api/v1`.
Opera SOLO sobre datos durables en Postgres (users/teams/planes); NO toca
el estado efímero del realtime (presencia/LSP) ni el server WS — un fallo
acá no puede tumbar la colaboración. NO es API pública: es la consola del
operador de la plataforma (vos), autenticada con un token de operador.

`service.py` = lógica pura sobre los stores (sandbox-testeable). `app.py`
= la cáscara ASGI (starlette; import diferido, verificada en VPS, mismo
patrón que pyright/asyncpg: el sandbox sin internet no la importa).
"""
