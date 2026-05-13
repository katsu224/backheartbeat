from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.couple_repo import CoupleRepository
from app.repositories.user_repo import UserRepository
from app.schemas.trigger import TriggerResponse
from app.services.connection_manager import manager
from app.services.fcm_service import send_fcm_notification

logger = structlog.get_logger()
router = APIRouter(prefix="/trigger", tags=["trigger"])


@router.post("/send", response_model=TriggerResponse)
async def send_trigger(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)

    if not couple:
        logger.info("trigger_no_couple", user_id=str(current_user.user_id))
        return TriggerResponse(delivered=False, method="offline")

    partner_id = (
        couple.user_b_id
        if couple.user_a_id == current_user.user_id
        else couple.user_a_id
    )

    if not partner_id:
        return TriggerResponse(delivered=False, method="offline")

    payload = {
        "type": "incoming_trigger",
        "from_name": current_user.name,
        "message": "Tu pareja te envió una señal ❤️",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if await manager.send_to_user(partner_id, payload):
        logger.info(
            "trigger_websocket",
            from_user=str(current_user.user_id),
            to_user=str(partner_id),
        )
        return TriggerResponse(delivered=True, method="websocket")

    partner = await UserRepository(db).get_by_id(partner_id)
    if partner and partner.fcm_token:
        if await send_fcm_notification(partner.fcm_token, current_user.name):
            logger.info(
                "trigger_fcm",
                from_user=str(current_user.user_id),
                to_user=str(partner_id),
            )
            return TriggerResponse(delivered=True, method="fcm")

    logger.info(
        "trigger_offline",
        from_user=str(current_user.user_id),
        to_user=str(partner_id),
    )
    return TriggerResponse(delivered=False, method="offline")
