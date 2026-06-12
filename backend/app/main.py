import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import simulator
from .database import init_db
from .routers import admin, boosts, referrals, subscriptions, trades, users
from .ws_manager import manager

_stop_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _stop_event.clear()
    task = asyncio.create_task(simulator.run_simulator(_stop_event))
    try:
        yield
    finally:
        _stop_event.set()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title="TradeSim — учебный симулятор (DEMO)",
    description=(
        "Учебный симулятор. Все сделки, балансы и блокчейн-данные виртуальные и "
        "сгенерированы программно. Реальные деньги не используются."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(trades.router)
app.include_router(subscriptions.router)
app.include_router(boosts.router)
app.include_router(referrals.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok", "demo": True, "ws_connections": manager.count}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    await ws.send_json({"type": "hello", "demo": True, "counters": simulator.get_counters()})
    try:
        while True:
            # We don't need client input; keep the socket alive.
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)
