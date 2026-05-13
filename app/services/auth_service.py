import random
import string

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.repositories.couple_repo import CoupleRepository
from app.repositories.user_repo import UserRepository

logger = structlog.get_logger()


def _generate_pairing_code() -> str:
    letters = random.choices(string.ascii_uppercase, k=4)
    digits = random.choices(string.digits, k=2)
    chars = letters + digits
    random.shuffle(chars)
    return "".join(chars)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.couple_repo = CoupleRepository(db)

    async def create_user(self, name: str) -> dict:
        user = await self.user_repo.create(name=name, auth_token="")
        token = create_access_token(user.user_id)
        await self.user_repo.update_auth_token(user.user_id, token)

        pairing_code = _generate_pairing_code()
        couple = await self.couple_repo.create(
            pairing_code=pairing_code, user_a_id=user.user_id
        )

        await self.db.commit()
        logger.info("user_created", user_id=str(user.user_id), pairing_code=pairing_code)

        return {
            "user_id": str(user.user_id),
            "auth_token": token,
            "pairing_code": pairing_code,
            "name": name,
        }

    async def join_couple(self, name: str, pairing_code: str) -> dict:
        couple = await self.couple_repo.get_by_pairing_code(pairing_code)
        if not couple or couple.is_complete:
            raise ValueError("Invalid or already used pairing code")

        user = await self.user_repo.create(name=name, auth_token="")
        token = create_access_token(user.user_id)
        await self.user_repo.update_auth_token(user.user_id, token)

        updated_couple = await self.couple_repo.complete_couple(couple.couple_id, user.user_id)

        await self.db.commit()
        logger.info(
            "couple_joined",
            user_id=str(user.user_id),
            couple_id=str(updated_couple.couple_id),
        )

        return {
            "user_id": str(user.user_id),
            "auth_token": token,
            "couple_id": str(updated_couple.couple_id),
            "name": name,
        }
