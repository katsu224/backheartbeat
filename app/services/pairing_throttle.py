import asyncio
import time
import uuid

import structlog

from app.services.connection_manager import manager as ws_manager

logger = structlog.get_logger()


FAIL_WINDOW_SECONDS = 300       # 5 min window
FAIL_THRESHOLD = 5              # max invalid attempts before lockout
LOCKOUT_SECONDS = 900           # 15 min lockout


class PairingThrottle:
    """Tracks failed pairing attempts per user and applies a lockout.

    Uses Redis when ``ws_manager`` has a Redis connection initialised
    (so it shares infrastructure with the WebSocket fan-out — no extra
    deployment). Falls back to an in-process counter when Redis is not
    configured; that fallback only protects against attackers on the
    same worker, which is acceptable for the single-worker mode where
    Redis is absent."""

    _local_fail_log: dict[str, list[float]] = {}
    _local_lockout: dict[str, float] = {}
    _lock = asyncio.Lock()

    @staticmethod
    def _fail_key(user_id: uuid.UUID) -> str:
        return f"pairing:fail:{user_id}"

    @staticmethod
    def _lock_key(user_id: uuid.UUID) -> str:
        return f"pairing:lock:{user_id}"

    @classmethod
    async def assert_not_locked(cls, user_id: uuid.UUID) -> None:
        redis = ws_manager._redis  # noqa: SLF001 — internal reuse by design
        if redis is not None:
            if await redis.exists(cls._lock_key(user_id)):
                raise PairingLockedError()
            return

        async with cls._lock:
            until = cls._local_lockout.get(str(user_id))
            if until and until > time.monotonic():
                raise PairingLockedError()

    @classmethod
    async def record_failure(cls, user_id: uuid.UUID) -> None:
        redis = ws_manager._redis  # noqa: SLF001
        if redis is not None:
            key = cls._fail_key(user_id)
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, FAIL_WINDOW_SECONDS)
            if count >= FAIL_THRESHOLD:
                await redis.set(cls._lock_key(user_id), "1", ex=LOCKOUT_SECONDS)
                await redis.delete(key)
                logger.info("pairing_locked", user_id=str(user_id))
            return

        async with cls._lock:
            now = time.monotonic()
            key = str(user_id)
            history = [t for t in cls._local_fail_log.get(key, []) if now - t < FAIL_WINDOW_SECONDS]
            history.append(now)
            cls._local_fail_log[key] = history
            if len(history) >= FAIL_THRESHOLD:
                cls._local_lockout[key] = now + LOCKOUT_SECONDS
                cls._local_fail_log.pop(key, None)
                logger.info("pairing_locked_local", user_id=str(user_id))

    @classmethod
    async def record_success(cls, user_id: uuid.UUID) -> None:
        redis = ws_manager._redis  # noqa: SLF001
        if redis is not None:
            await redis.delete(cls._fail_key(user_id))
            return
        async with cls._lock:
            cls._local_fail_log.pop(str(user_id), None)


class PairingLockedError(Exception):
    pass
