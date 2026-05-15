# Prototipo — capa cero

Estado compartido en tiempo real. Lo más mínimo posible para ver dos pestañas sincronizándose.

## Qué hace

- Levanta un servidor WebSocket en `ws://localhost:8765`.
- Mantiene **un solo documento** (un string) en memoria.
- Cualquier cliente que se conecta recibe el estado actual.
- Cuando un cliente edita, el cambio se retransmite a todos los demás conectados.

## Qué NO hace todavía

- No persiste nada (si reinicias el servidor, el documento se pierde).
- No maneja edición concurrente real (si dos personas escriben **al mismo tiempo en la misma posición**, una sobreescribe a la otra — last-write-wins).
- No hay autenticación, no hay múltiples documentos, no hay ownership, no hay análisis semántico. Nada.

Eso está bien. Es la **capa cero**. Lo demás se monta encima.

## Cómo correrlo

```bash
cd prototype
pip install -r requirements.txt
python server.py
```

Luego abre `index.html` en dos o tres pestañas del navegador. Escribe en una. Mira las otras.

## El momento mágico que validamos

Tres pestañas. Escribes en cualquiera. Aparece en las otras dos instantáneamente. Cierras una, las demás siguen funcionando. Abres una cuarta más tarde, recibe el contenido completo.

Si eso funciona, la base del producto es real.

## Lo que rompe a propósito

- Pestañas A y B teclean al mismo tiempo → caracteres se pueden perder.
- Reiniciar servidor → documento se borra.
- Conexión cae → no hay reconexión automática.

Todo eso se arregla en capas posteriores (CRDT real, persistencia, reconexión). No es un bug, es alcance.

## Estructura

- `server.py` — servidor WebSocket. ~35 líneas.
- `index.html` — cliente mínimo con un textarea.
- `requirements.txt` — solo `websockets`.
