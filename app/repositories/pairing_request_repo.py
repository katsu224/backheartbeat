import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pairing_request import PairingRequest


class PairingRequestRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self, from_user_id: uuid.UUID, to_user_id: uuid.UUID, pairing_code: str
    ) -> PairingRequest:
        req = PairingRequest(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            pairing_code=pairing_code,
        )
        self.db.add(req)
        await self.db.flush()
        await self.db.refresh(req)
        return req

    async def get_by_id(self, request_id: uuid.UUID) -> PairingRequest | None:
        result = await self.db.execute(
            select(PairingRequest).where(PairingRequest.request_id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_by_requester(self, from_user_id: uuid.UUID) -> PairingRequest | None:
        result = await self.db.execute(
            select(PairingRequest).where(
                PairingRequest.from_user_id == from_user_id,
                PairingRequest.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_pending_for_target(self, to_user_id: uuid.UUID) -> PairingRequest | None:
        result = await self.db.execute(
            select(PairingRequest)
            .where(
                PairingRequest.to_user_id == to_user_id,
                PairingRequest.status == "pending",
            )
            .order_by(PairingRequest.created_at.desc())
        )
        return result.scalars().first()

    async def cancel_all_pending_for_target(self, to_user_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(PairingRequest).where(
                PairingRequest.to_user_id == to_user_id,
                PairingRequest.status == "pending",
            )
        )
        for req in result.scalars().all():
            req.status = "cancelled"
        await self.db.flush()

    async def cancel_all_involving_user(self, user_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(PairingRequest).where(
                (PairingRequest.from_user_id == user_id) | (PairingRequest.to_user_id == user_id),
                PairingRequest.status == "pending",
            )
        )
        for req in result.scalars().all():
            req.status = "cancelled"
        await self.db.flush()
