import asyncio
import queue
import threading
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dhanhq.marketfeed import DhanFeed

router = APIRouter(tags=["WebSocket"])


def _normalize_instruments(rows: list[list[Any]]) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []
    for r in rows:
        if len(r) == 2:
            out.append((int(r[0]), str(r[1])))
        elif len(r) == 3:
            out.append((int(r[0]), str(r[1]), int(r[2])))
        else:
            raise ValueError("Each instrument must be [exchange, security_id] or [exchange, security_id, mode]")
    return out


def _json_safe(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _json_safe(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_json_safe(v) for v in data]
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    return str(data)


@router.websocket("/market-feed")
async def market_feed_ws(websocket: WebSocket) -> None:
    """First message must be JSON: `instruments` (list of lists) and optional `version` (`v1` or `v2`)."""
    await websocket.accept()
    d = websocket.app.state.dhan
    try:
        payload = await websocket.receive_json()
    except Exception:
        await websocket.close(code=4400)
        return
    try:
        instruments = _normalize_instruments(payload["instruments"])
    except (KeyError, TypeError, ValueError) as e:
        await websocket.send_json({"type": "error", "message": f"Invalid instruments: {e}"})
        await websocket.close(code=4400)
        return
    version = str(payload.get("version", "v2"))
    out_q: queue.Queue = queue.Queue()
    stop = threading.Event()

    def worker() -> None:
        feed = DhanFeed(d.client_id, d.access_token, instruments, version=version)
        try:
            feed.run_forever()
            while not stop.is_set():
                data = feed.get_data()
                out_q.put(_json_safe(data))
        except Exception as ex:  # noqa: BLE001
            out_q.put({"type": "error", "message": str(ex)})
        finally:
            try:
                feed.close_connection()
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()

    async def forward() -> None:
        try:
            while not stop.is_set():
                data = await asyncio.to_thread(out_q.get)
                await websocket.send_json(data)
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(forward())
    try:
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
