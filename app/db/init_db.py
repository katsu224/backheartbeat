import structlog
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_fixed

from app.db.session import engine

logger = structlog.get_logger()


@retry(stop=stop_after_attempt(10), wait=wait_fixed(3))
async def _wait_for_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def init_db() -> None:
    await _wait_for_db()

    async with engine.connect() as conn:
        try:
            row = (
                await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            ).fetchone()
        except Exception as exc:
            logger.error("database_migrations_missing", error=str(exc))
            raise RuntimeError(
                "alembic_version table not found — run 'alembic upgrade head' before starting"
            ) from exc
        if row is None:
            raise RuntimeError(
                "No Alembic migrations applied — run 'alembic upgrade head' before starting"
            )

    logger.info("database_ready")
