import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.couple_repo import CoupleRepository
from app.repositories.pairing_request_repo import PairingRequestRepository
from app.repositories.user_repo import UserRepository
from app.services.auth_service import _generate_pairing_code
from app.services.connection_manager import manager

logger = structlog.get_logger()


def _random_code() -> str:
    return _generate_pairing_code()


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

        # Reject if the code owner is currently paired (their pending couple persists while paired)
        owner_paired = await self.couple_repo.get_by_user_id(couple.user_a_id)
        if owner_paired:
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

    # ── STATS ─────────────────────────────────────────────────────────────────

    async def get_stats(self, current_user_id: uuid.UUID) -> dict:
        couple = await self.couple_repo.get_by_user_id(current_user_id)
        if not couple:
            raise ValueError("NOT_PAIRED")
        paired_since = couple.paired_at or couple.created_at
        days = (datetime.now(timezone.utc) - paired_since).days
        return {"days_together": days, "paired_since": paired_since.date()}

    # ── UNPAIR ────────────────────────────────────────────────────────────────

    async def unpair(self, current_user_id: uuid.UUID) -> dict:
        couple = await self.couple_repo.get_by_user_id(current_user_id)
        if not couple:
            raise ValueError("NOT_PAIRED")

        user_a_id = couple.user_a_id
        user_b_id = couple.user_b_id
        partner_id = user_b_id if user_a_id == current_user_id else user_a_id
        # The complete couple row IS user_a's original pending couple (same row, mutated).
        # Save their code before deleting.
        original_a_code = couple.pairing_code

        await self.req_repo.cancel_all_involving_user(current_user_id)
        if partner_id:
            await self.req_repo.cancel_all_involving_user(partner_id)

        await self.db.delete(couple)
        await self.db.flush()

        # Restore user_a's pending couple with their original code.
        await self.couple_repo.create(original_a_code, user_a_id)

        # user_b's pending couple was preserved during accept_pairing; look it up.
        b_pending = await self.couple_repo.get_pending_by_user_id(user_b_id) if user_b_id else None
        if user_b_id and not b_pending:
            # Fallback: if somehow lost, generate a new code.
            b_code = _random_code()
            await self.couple_repo.create(b_code, user_b_id)
        else:
            b_code = b_pending.pairing_code if b_pending else None

        my_code = original_a_code if current_user_id == user_a_id else b_code

        if partner_id:
            partner_code = b_code if partner_id == user_b_id else original_a_code
            await manager.send_to_user(
                partner_id,
                {"type": "unpaired", "new_pairing_code": partner_code},
            )

        await self.db.commit()
        logger.info("unpaired", user=str(current_user_id), partner=str(partner_id))
        return {"status": "unpaired", "new_pairing_code": my_code}
