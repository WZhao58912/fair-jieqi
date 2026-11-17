"""FastAPI entrypoint: HTTP health check + the game WebSocket route."""

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .ws.manager import manager

app = FastAPI(title="Provably Fair Jieqi", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local dev; tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "rooms": len(manager.rooms)}


@app.websocket("/ws")
async def game_ws(websocket: WebSocket) -> None:
    await manager.handle(websocket)
