import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, username: str, name: str, password_hash: str) -> User:
        user = User(username=username, name=name, password_hash=password_hash)
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def update_auth_token(self, user_id: uuid.UUID, auth_token: str) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.auth_token = auth_token
            await self.db.flush()

    async def update_fcm_token(self, user_id: uuid.UUID, fcm_token: str) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False
        user.fcm_token = fcm_token
        await self.db.flush()
        return True

    async def update_profile(self, user_id: uuid.UUID, name: str | None) -> User | None:
        user = await self.get_by_id(user_id)
        if not user:
            return None
        if name is not None:
            user.name = name
        await self.db.flush()
        return user

    async def update_avatar_path(self, user_id: uuid.UUID, avatar_path: str | None) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False
        user.avatar_path = avatar_path
        await self.db.flush()
        return True
