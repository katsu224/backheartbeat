import random
import string
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.couple_repo import CoupleRepository
from app.repositories.pairing_request_repo import PairingRequestRepository
from app.repositories.user_repo import UserRepository
from app.services.connection_manager import manager

logger = structlog.get_logger()


def _random_code() -> str:
    chars = random.choices(string.ascii_uppercase, k=4) + random.choices(string.digits, k=2)
    random.shuffle(chars)
    return "".join(chars)


class CoupleService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.couple_repo = CoupleRepository(db)
        self.req_repo = PairingRequestRepository(db)

    # ── REQUEST ───────────────────────────────────────────────────────────────

    async def request_pairing(self, from_user_id: uuid.UUID, pairing_code: str) -> dict:
        couple = await self.couple_repo.get_by_pairing_code(pairing_code)
        if not couple or couple.is_complete:
            raise ValueError("INVALID_PAIRING_CODE")

        if couple.user_a_id == from_user_id:
            raise ValueError("CANNOT_JOIN_OWN_CODE")

        already_paired = await self.couple_repo.get_by_user_id(from_user_id)
        if already_paired:
            raise ValueError("ALREADY_PAIRED")

        # Cancel any previous pending request from this user
        old_req = await self.req_repo.get_pending_by_requester(from_user_id)
        if old_req:
            old_req.status = "cancelled"
            await self.db.flush()

        from_user = await self.user_repo.get_by_id(from_user_id)
        to_user_id = couple.user_a_id

        req = await self.req_repo.create(from_user_id, to_user_id, pairing_code)

        # Notify target in real time (if online)
        await manager.send_to_user(
            to_user_id,
            {
                "type": "pairing_request",
                "request_id": str(req.request_id),
                "from_name": from_user.name,
                "from_username": from_user.username,
            },
        )

        await self.db.commit()
        logger.info("pairing_requested", from_user=str(from_user_id), to_user=str(to_user_id))
        return {"request_id": str(req.request_id), "status": "pending"}

    # ── ACCEPT ────────────────────────────────────────────────────────────────

    async def accept_pairing(self, request_id: uuid.UUID, current_user_id: uuid.UUID) -> dict:
        req = await self.req_repo.get_by_id(request_id)
        if not req or req.status != "pending":
            raise ValueError("INVALID_REQUEST")
        if req.to_user_id != current_user_id:
            raise ValueError("NOT_AUTHORIZED")

        couple = await self.couple_repo.get_by_pairing_code(req.pairing_code)
        if not couple or couple.is_complete:
            raise ValueError("PAIRING_EXPIRED")

        # Delete requester's own dangling pending couple
        b_pending = await self.couple_repo.get_pending_by_user_id(req.from_user_id)
        if b_pending:
            await self.db.delete(b_pending)
            await self.db.flush()

        # Cancel all other pending requests to current user
        await self.req_repo.cancel_all_pending_for_target(current_user_id)

        # Complete the couple
        updated = await self.couple_repo.complete_couple(couple.couple_id, req.from_user_id)
        req.status = "accepted"
        await self.db.flush()

        from_user = await self.user_repo.get_by_id(req.from_user_id)
        to_user = await self.user_repo.get_by_id(current_user_id)

        # Notify requester (B): accepted
        await manager.send_to_user(
            req.from_user_id,
            {
                "type": "pairing_accepted",
                "partner_name": to_user.name,
                "couple_id": str(updated.couple_id),
            },
        )

        # Notify acceptor (A): paired (UI refresh)
        await manager.send_to_user(
            current_user_id,
            {
                "type": "paired",
                "partner_name": from_user.name,
                "couple_id": str(updated.couple_id),
            },
        )

        await self.db.commit()
        logger.info("pairing_accepted", couple_id=str(updated.couple_id))
        return {
            "status": "accepted",
            "partner_name": from_user.name,
            "couple_id": str(updated.couple_id),
        }

    # ── REJECT ────────────────────────────────────────────────────────────────

    async def reject_pairing(self, request_id: uuid.UUID, current_user_id: uuid.UUID) -> dict:
        req = await self.req_repo.get_by_id(request_id)
        if not req or req.status != "pending":
            raise ValueError("INVALID_REQUEST")
        if req.to_user_id != current_user_id:
            raise ValueError("NOT_AUTHORIZED")

        req.status = "rejected"
        await self.db.flush()

        await manager.send_to_user(req.from_user_id, {"type": "pairing_rejected"})

        await self.db.commit()
        logger.info("pairing_rejected", request_id=str(request_id))
        return {"status": "rejected"}

    # ── UNPAIR ────────────────────────────────────────────────────────────────

    async def unpair(self, current_user_id: uuid.UUID) -> dict:
        couple = await self.couple_repo.get_by_user_id(current_user_id)
        if not couple:
            raise ValueError("NOT_PAIRED")

        partner_id = (
            couple.user_b_id
            if couple.user_a_id == current_user_id
            else couple.user_a_id
        )

        # Cancel pending requests involving both users
        await self.req_repo.cancel_all_involving_user(current_user_id)
        if partner_id:
            await self.req_repo.cancel_all_involving_user(partner_id)

        # Delete the couple
        await self.db.delete(couple)
        await self.db.flush()

        # Auto-generate fresh pairing codes for both
        my_code = _random_code()
        await self.couple_repo.create(my_code, current_user_id)

        partner_code: str | None = None
        if partner_id:
            partner_code = _random_code()
            await self.couple_repo.create(partner_code, partner_id)
            await manager.send_to_user(
                partner_id,
                {"type": "unpaired", "new_pairing_code": partner_code},
            )

        await self.db.commit()
        logger.info("unpaired", user=str(current_user_id), partner=str(partner_id))
        return {"status": "unpaired", "new_pairing_code": my_code}
