import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.couple import Couple


class CoupleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, pairing_code: str, user_a_id: uuid.UUID) -> Couple:
        couple = Couple(pairing_code=pairing_code, user_a_id=user_a_id)
        self.db.add(couple)
        await self.db.flush()
        await self.db.refresh(couple)
        return couple

    async def get_by_id(self, couple_id: uuid.UUID) -> Couple | None:
        result = await self.db.execute(
            select(Couple).where(Couple.couple_id == couple_id)
        )
        return result.scalar_one_or_none()

    async def get_by_pairing_code(self, code: str) -> Couple | None:
        result = await self.db.execute(
            select(Couple).where(Couple.pairing_code == code)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: uuid.UUID) -> Couple | None:
        result = await self.db.execute(
            select(Couple).where(
                or_(Couple.user_a_id == user_id, Couple.user_b_id == user_id),
                Couple.is_complete.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_by_user_id(self, user_id: uuid.UUID) -> Couple | None:
        result = await self.db.execute(
            select(Couple).where(
                Couple.user_a_id == user_id,
                Couple.is_complete.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def complete_couple(self, couple_id: uuid.UUID, user_b_id: uuid.UUID) -> Couple:
        couple = await self.get_by_id(couple_id)
        couple.user_b_id = user_b_id
        couple.is_complete = True
        couple.paired_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(couple)
        return couple
