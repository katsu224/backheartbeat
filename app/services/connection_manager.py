import asyncio
import json
import uuid

import redis.asyncio as aioredis
import structlog
from fastapi import WebSocket

from app.core.config import settings

logger = structlog.get_logger()

DELIVERY_CHANNEL = "ws:deliver"
PRESENCE_TTL_SECONDS = 60


class ConnectionManager:
    """WebSocket connection manager with optional Redis pub/sub fan-out.

    With ``REDIS_URL`` empty, behaves as a single-process in-memory manager
    (the legacy mode, suitable for one uvicorn worker).

    With ``REDIS_URL`` set, each worker:
    - Tracks its own WebSocket objects locally in ``_connections``.
    - Mirrors presence to Redis via ``ws:online:{user_id}`` keys with a TTL
      that must be refreshed (see ``refresh_presence``).
    - On ``send_to_user``: delivers locally if the target is connected here;
      otherwise publishes the payload to ``ws:deliver`` so the worker holding
      the target's WebSocket can relay it.
    """

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._redis: aioredis.Redis | None = None
        self._subscriber_task: asyncio.Task | None = None

    async def init(self) -> None:
        if not settings.REDIS_URL:
            logger.info("ws_manager_local_only")
            return
        self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        self._subscriber_task = asyncio.create_task(self._subscribe_loop())
        logger.info("ws_manager_redis_initialized")

    async def shutdown(self) -> None:
        if self._subscriber_task:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass

    async def connect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        key = str(user_id)
        self._connections[key] = websocket
        await self._mark_online(key)
        logger.info("ws_connected", user_id=key, total=len(self._connections))

    def disconnect(self, user_id: uuid.UUID) -> None:
        key = str(user_id)
        if self._connections.pop(key, None) is None:
            return
        if self._redis:
            asyncio.create_task(self._clear_online(key))
        logger.info("ws_disconnected", user_id=key, total=len(self._connections))

    async def refresh_presence(self, user_id: uuid.UUID) -> None:
        if str(user_id) in self._connections:
            await self._mark_online(str(user_id))

    async def is_connected(self, user_id: uuid.UUID) -> bool:
        key = str(user_id)
        if key in self._connections:
            return True
        if self._redis:
            return bool(await self._redis.exists(f"ws:online:{key}"))
        return False

    async def send_to_user(self, user_id: uuid.UUID, message: dict) -> bool:
        key = str(user_id)
        ws = self._connections.get(key)
        if ws is not None:
            return await self._deliver_local(key, ws, message)

        if not self._redis:
            return False

        if not await self._redis.exists(f"ws:online:{key}"):
            return False

        try:
            await self._redis.publish(
                DELIVERY_CHANNEL,
                json.dumps({"user_id": key, "message": message}),
            )
            return True
        except Exception as exc:
            logger.warning("ws_publish_failed", user_id=key, error=str(exc))
            return False

    async def _deliver_local(self, key: str, ws: WebSocket, message: dict) -> bool:
        try:
            await ws.send_json(message)
            return True
        except Exception as exc:
            logger.warning("ws_send_failed", user_id=key, error=str(exc))
            self._connections.pop(key, None)
            if self._redis:
                await self._clear_online(key)
            return False

    async def _mark_online(self, key: str) -> None:
        if not self._redis:
            return
        try:
            await self._redis.set(f"ws:online:{key}", "1", ex=PRESENCE_TTL_SECONDS)
        except Exception as exc:
            logger.warning("ws_presence_set_failed", user_id=key, error=str(exc))

    async def _clear_online(self, key: str) -> None:
        if not self._redis:
            return
        try:
            await self._redis.delete(f"ws:online:{key}")
        except Exception as exc:
            logger.warning("ws_presence_clear_failed", user_id=key, error=str(exc))

    async def _subscribe_loop(self) -> None:
        if not self._redis:
            return
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(DELIVERY_CHANNEL)
            async for raw in pubsub.listen():
                if raw is None or raw.get("type") != "message":
                    continue
                try:
                    data = json.loads(raw["data"])
                    target = data["user_id"]
                    message = data["message"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
                ws = self._connections.get(target)
                if ws is None:
                    continue
                try:
                    await ws.send_json(message)
                except Exception as exc:
                    logger.warning("ws_relay_failed", user_id=target, error=str(exc))
                    self._connections.pop(target, None)
                    await self._clear_online(target)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("ws_subscribe_loop_error", error=str(exc))
        finally:
            try:
                await pubsub.unsubscribe(DELIVERY_CHANNEL)
                await pubsub.aclose()
            except Exception:
                pass


manager = ConnectionManager()
