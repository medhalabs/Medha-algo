import queue
from typing import Any

from dhanhq.orderupdate import OrderSocket


class OrderSocketBridge(OrderSocket):
    """Forwards Dhan order-update payloads to a thread-safe queue."""

    def __init__(self, client_id: str, access_token: str, out_queue: queue.Queue) -> None:
        super().__init__(client_id, access_token)
        self._out_queue = out_queue

    async def handle_order_update(self, order_update: dict[str, Any]) -> None:  # type: ignore[override]
        self._out_queue.put(order_update)
