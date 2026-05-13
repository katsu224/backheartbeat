import uuid

import structlog
from fastapi import WebSocket

logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        key = str(user_id)
        self._connections[key] = websocket
        logger.info("ws_connected", user_id=key, total=len(self._connections))

    def disconnect(self, user_id: uuid.UUID) -> None:
        key = str(user_id)
        self._connections.pop(key, None)
        logger.info("ws_disconnected", user_id=key, total=len(self._connections))

    def is_connected(self, user_id: uuid.UUID) -> bool:
        return str(user_id) in self._connections

    async def send_to_user(self, user_id: uuid.UUID, message: dict) -> bool:
        key = str(user_id)
        ws = self._connections.get(key)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception as exc:
            logger.warning("ws_send_failed", user_id=key, error=str(exc))
            self._connections.pop(key, None)
            return False


manager = ConnectionManager()
