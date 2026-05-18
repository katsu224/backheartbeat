import secrets

import structlog
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.repositories.couple_repo import CoupleRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository

logger = structlog.get_logger()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# Excludes visually ambiguous characters (0/O, 1/I/L) for usability.
PAIRING_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 31 chars
PAIRING_CODE_LENGTH = 8


def _generate_pairing_code() -> str:
    """Cryptographically random 8-char code. Entropy ~= log2(31^8) ≈ 39.6 bits."""
    return "".join(secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.couple_repo = CoupleRepository(db)
        self.refresh_repo = RefreshTokenRepository(db)

    async def register(self, username: str, name: str, password: str) -> dict:
        existing = await self.user_repo.get_by_username(username)
        if existing:
            raise ValueError("USERNAME_TAKEN")

        user = await self.user_repo.create(
            username=username,
            name=name,
            password_hash=hash_password(password),
        )
        access_token = create_access_token(user.user_id)
        refresh_plain, _ = await self.refresh_repo.issue(user.user_id)
        await self.user_repo.update_auth_token(user.user_id, access_token)

        pairing_code = _generate_pairing_code()
        await self.couple_repo.create(pairing_code=pairing_code, user_a_id=user.user_id)

        await self.db.commit()
        logger.info("user_registered", user_id=str(user.user_id), username=username)

        return {
            "user_id": str(user.user_id),
            "auth_token": access_token,
            "access_token": access_token,
            "refresh_token": refresh_plain,
            "access_expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "pairing_code": pairing_code,
            "name": name,
            "username": username,
        }

    async def login(self, username: str, password: str) -> dict:
        user = await self.user_repo.get_by_username(username)
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("INVALID_CREDENTIALS")

        access_token = create_access_token(user.user_id)
        refresh_plain, _ = await self.refresh_repo.issue(user.user_id)
        await self.user_repo.update_auth_token(user.user_id, access_token)

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
            "auth_token": access_token,
            "access_token": access_token,
            "refresh_token": refresh_plain,
            "access_expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "name": user.name,
            "username": user.username,
            "is_paired": is_paired,
            "pairing_code": pairing_code,
        }

    async def refresh(self, refresh_token_plain: str) -> dict:
        existing = await self.refresh_repo.get_active(refresh_token_plain)
        if not existing:
            raise ValueError("INVALID_REFRESH_TOKEN")

        await self.refresh_repo.revoke(existing.token_id)
        new_refresh_plain, _ = await self.refresh_repo.issue(existing.user_id)
        access_token = create_access_token(existing.user_id)

        await self.db.commit()
        logger.info("token_refreshed", user_id=str(existing.user_id))

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_plain,
            "access_expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    async def logout(self, refresh_token_plain: str | None) -> None:
        if not refresh_token_plain:
            return
        existing = await self.refresh_repo.get_active(refresh_token_plain)
        if existing:
            await self.refresh_repo.revoke(existing.token_id)
            await self.db.commit()
            logger.info("user_logged_out", user_id=str(existing.user_id))

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
