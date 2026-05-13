import random
import string

import structlog
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.repositories.couple_repo import CoupleRepository
from app.repositories.user_repo import UserRepository

logger = structlog.get_logger()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _generate_pairing_code() -> str:
    chars = random.choices(string.ascii_uppercase, k=4) + random.choices(string.digits, k=2)
    random.shuffle(chars)
    return "".join(chars)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.couple_repo = CoupleRepository(db)

    async def register(self, username: str, name: str, password: str) -> dict:
        existing = await self.user_repo.get_by_username(username)
        if existing:
            raise ValueError("USERNAME_TAKEN")

        user = await self.user_repo.create(
            username=username,
            name=name,
            password_hash=hash_password(password),
        )
        token = create_access_token(user.user_id)
        await self.user_repo.update_auth_token(user.user_id, token)

        pairing_code = _generate_pairing_code()
        await self.couple_repo.create(pairing_code=pairing_code, user_a_id=user.user_id)

        await self.db.commit()
        logger.info("user_registered", user_id=str(user.user_id), username=username)

        return {
            "user_id": str(user.user_id),
            "auth_token": token,
            "pairing_code": pairing_code,
            "name": name,
            "username": username,
        }

    async def login(self, username: str, password: str) -> dict:
        user = await self.user_repo.get_by_username(username)
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("INVALID_CREDENTIALS")

        token = create_access_token(user.user_id)
        await self.user_repo.update_auth_token(user.user_id, token)

        couple = await self.couple_repo.get_by_user_id(user.user_id)
        pairing_code: str | None = None
        is_paired = False

        if couple and couple.is_complete:
            is_paired = True
        else:
            pending = await self.couple_repo.get_pending_by_user_id(user.user_id)
            if pending:
                pairing_code = pending.pairing_code

        await self.db.commit()
        logger.info("user_logged_in", user_id=str(user.user_id), username=username)

        return {
            "user_id": str(user.user_id),
            "auth_token": token,
            "name": user.name,
            "username": user.username,
            "is_paired": is_paired,
            "pairing_code": pairing_code,
        }

    async def join_couple(self, current_user_id, pairing_code: str) -> dict:
        couple = await self.couple_repo.get_by_pairing_code(pairing_code)

        if not couple or couple.is_complete:
            raise ValueError("INVALID_PAIRING_CODE")

        if couple.user_a_id == current_user_id:
            raise ValueError("CANNOT_JOIN_OWN_CODE")

        # Delete the joining user's own pending couple (they won't need it)
        own_pending = await self.couple_repo.get_pending_by_user_id(current_user_id)
        if own_pending:
            await self.db.delete(own_pending)
            await self.db.flush()

        updated = await self.couple_repo.complete_couple(couple.couple_id, current_user_id)

        partner_repo = UserRepository(self.db)
        partner = await partner_repo.get_by_id(couple.user_a_id)

        await self.db.commit()
        logger.info("couple_joined", user_b=str(current_user_id), couple_id=str(updated.couple_id))

        return {
            "couple_id": str(updated.couple_id),
            "partner_name": partner.name if partner else "Unknown",
        }
