import uuid
from pathlib import Path

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_media import UserMedia

logger = structlog.get_logger()


class UserMediaRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_file_path(self, file_path: str) -> UserMedia | None:
        result = await self.db.execute(
            select(UserMedia).where(UserMedia.file_path == file_path)
        )
        return result.scalar_one_or_none()

    async def get_owner_by_path_prefix(self, dir_prefix: str, media_id: uuid.UUID) -> UserMedia | None:
        """Locate the row whose file_path matches ``{dir_prefix}/{media_id}.*``."""
        result = await self.db.execute(
            select(UserMedia).where(UserMedia.file_path.like(f"{dir_prefix}/{media_id}.%"))
        )
        return result.scalar_one_or_none()

    async def record(
        self,
        user_id: uuid.UUID,
        media_type: str,
        file_path: str,
        size_bytes: int,
    ) -> UserMedia:
        row = UserMedia(
            user_id=user_id,
            media_type=media_type,
            file_path=file_path,
            size_bytes=size_bytes,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def count(self, user_id: uuid.UUID, media_type: str) -> int:
        result = await self.db.execute(
            select(func.count(UserMedia.media_id)).where(
                UserMedia.user_id == user_id,
                UserMedia.media_type == media_type,
            )
        )
        return int(result.scalar() or 0)

    async def oldest(self, user_id: uuid.UUID, media_type: str, limit: int) -> list[UserMedia]:
        result = await self.db.execute(
            select(UserMedia)
            .where(UserMedia.user_id == user_id, UserMedia.media_type == media_type)
            .order_by(UserMedia.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_rows(self, media_ids: list[uuid.UUID]) -> None:
        if not media_ids:
            return
        await self.db.execute(
            delete(UserMedia).where(UserMedia.media_id.in_(media_ids))
        )

    async def enforce_quota(
        self,
        user_id: uuid.UUID,
        media_type: str,
        quota: int,
    ) -> None:
        """If the user has more than ``quota`` rows of ``media_type``, delete
        the oldest ones (both the DB row and the underlying file) until
        the count is back at the quota."""
        current = await self.count(user_id, media_type)
        excess = current - quota
        if excess <= 0:
            return

        victims = await self.oldest(user_id, media_type, excess)
        for victim in victims:
            try:
                Path(victim.file_path).unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("media_unlink_failed", path=victim.file_path, error=str(exc))
        await self.delete_rows([v.media_id for v in victims])
