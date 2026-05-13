import structlog
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_fixed

from app.db.session import engine

logger = structlog.get_logger()


@retry(stop=stop_after_attempt(10), wait=wait_fixed(3))
async def init_db() -> None:
    try:
        # Alembic maneja las migraciones, por lo que aquí solo probamos la conexión
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("database_ready")
    except Exception as exc:
        logger.error("database_init_failed", error=str(exc))
        raise
