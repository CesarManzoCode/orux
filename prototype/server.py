import asyncio
import json
from websockets.asyncio.server import serve

clients = set()
document = ""


async def broadcast(sender, message):
    for client in list(clients):
        if client is sender:
            continue
        try:
            await client.send(message)
        except Exception:
            clients.discard(client)


async def handler(websocket):
    global document
    clients.add(websocket)
    print(f"+ cliente conectado (total: {len(clients)})")
    try:
        await websocket.send(json.dumps({"type": "init", "content": document}))
        async for raw in websocket:
            data = json.loads(raw)
            if data.get("type") == "update":
                document = data.get("content", "")
                await broadcast(websocket, json.dumps({"type": "update", "content": document}))
    finally:
        clients.discard(websocket)
        print(f"- cliente desconectado (total: {len(clients)})")


async def main():
    async with serve(handler, "localhost", 8765):
        print("servidor escuchando en ws://localhost:8765")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
