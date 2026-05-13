import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.button import Button


class ButtonRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        couple_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        label: str,
    ) -> Button:
        button = Button(couple_id=couple_id, owner_user_id=owner_user_id, label=label)
        self.db.add(button)
        await self.db.flush()
        await self.db.refresh(button)
        return button

    async def get_by_id(self, button_id: uuid.UUID) -> Button | None:
        result = await self.db.execute(select(Button).where(Button.button_id == button_id))
        return result.scalar_one_or_none()

    async def list_by_couple(self, couple_id: uuid.UUID) -> list[Button]:
        result = await self.db.execute(
            select(Button).where(Button.couple_id == couple_id).order_by(Button.updated_at)
        )
        return list(result.scalars().all())

    async def update(self, button_id: uuid.UUID, label: str) -> Button | None:
        button = await self.get_by_id(button_id)
        if not button:
            return None
        button.label = label
        await self.db.flush()
        await self.db.refresh(button)
        return button

    async def delete(self, button_id: uuid.UUID) -> bool:
        button = await self.get_by_id(button_id)
        if not button:
            return False
        await self.db.delete(button)
        await self.db.flush()
        return True
