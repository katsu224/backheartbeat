import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_refresh_token, hash_refresh_token
from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def issue(self, user_id: uuid.UUID) -> tuple[str, RefreshToken]:
        """Generate a new refresh token, persist its hash, and return
        (plaintext_token, row). The plaintext is only available here."""
        plaintext = generate_refresh_token()
        token = RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(plaintext),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self.db.add(token)
        await self.db.flush()
        return plaintext, token

    async def get_active(self, plaintext: str) -> RefreshToken | None:
        token_hash = hash_refresh_token(plaintext)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        if row.revoked_at is not None:
            return None
        if row.expires_at <= datetime.now(timezone.utc):
            return None
        return row

    async def revoke(self, token_id: uuid.UUID) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_id == token_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
