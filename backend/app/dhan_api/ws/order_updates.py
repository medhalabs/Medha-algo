import asyncio
import queue
import threading
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.dhan_api.ws.order_socket_bridge import OrderSocketBridge

router = APIRouter(tags=["WebSocket"])


def _json_safe(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _json_safe(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_json_safe(v) for v in data]
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    return str(data)


def start_order_thread(app: Any) -> None:
    settings = get_settings()
    q: queue.Queue = app.state.order_queue

    def run() -> None:
        bridge = OrderSocketBridge(settings.dhan_client_id, settings.dhan_access_token, q)
        try:
            bridge.connect_to_dhan_websocket_sync()
        except Exception as ex:  # noqa: BLE001
            q.put({"type": "error", "source": "order_updates", "message": str(ex)})

    threading.Thread(target=run, daemon=True).start()


async def order_broadcast_loop(app: Any) -> None:
    while True:
        msg = await asyncio.to_thread(app.state.order_queue.get)
        safe = _json_safe(msg)
        dead: list[WebSocket] = []
        for ws in list(app.state.order_update_clients):
            try:
                await ws.send_json(safe)
            except Exception:
                dead.append(ws)
        for ws in dead:
            app.state.order_update_clients.discard(ws)


@router.websocket("/order-updates")
async def order_updates_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    websocket.app.state.order_update_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        websocket.app.state.order_update_clients.discard(websocket)
