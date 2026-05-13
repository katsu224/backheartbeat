import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.button_repo import ButtonRepository
from app.repositories.couple_repo import CoupleRepository
from app.repositories.user_repo import UserRepository
from app.schemas.trigger import TriggerBody, TriggerResponse
from app.services.connection_manager import manager
from app.services.fcm_service import send_fcm_notification

logger = structlog.get_logger()
router = APIRouter(prefix="/trigger", tags=["trigger"])


@router.post("/send", response_model=TriggerResponse)
async def send_trigger(
    request: Request,
    body: TriggerBody | None = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple:
        return TriggerResponse(delivered=False, method="offline")

    partner_id = (
        couple.user_b_id
        if couple.user_a_id == current_user.user_id
        else couple.user_a_id
    )
    if not partner_id:
        return TriggerResponse(delivered=False, method="offline")

    # Resolve button info
    button_label = ""
    video_url = ""
    bg_color = ""

    if body and body.button_id:
        try:
            btn = await ButtonRepository(db).get_by_id(uuid.UUID(body.button_id))
            if btn and btn.owner_user_id == current_user.user_id:
                button_label = btn.label
                if btn.video_url:
                    # Respect reverse-proxy headers so the URL is always HTTPS
                    proto = request.headers.get("x-forwarded-proto", "https")
                    host = request.headers.get("x-forwarded-host", "") or request.headers.get("host", "")
                    base = f"{proto}://{host}" if host else str(request.base_url).rstrip("/")
                    video_url = f"{base}{btn.video_url}"
                bg_color = btn.bg_color or ""
        except (ValueError, AttributeError):
            pass

    duration_seconds = body.duration_seconds if body else 0

    payload = {
        "type": "incoming_trigger",
        "from_name": current_user.name,
        "button_label": button_label,
        "video_url": video_url,
        "bg_color": bg_color,
        "duration_seconds": duration_seconds,
        "message": button_label or "Tu pareja te envió una señal ❤️",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if await manager.send_to_user(partner_id, payload):
        logger.info("trigger_websocket", from_user=str(current_user.user_id), to_user=str(partner_id))
        return TriggerResponse(delivered=True, method="websocket")

    partner = await UserRepository(db).get_by_id(partner_id)
    if partner and partner.fcm_token:
        if await send_fcm_notification(
            partner.fcm_token,
            current_user.name,
            button_label=button_label,
            video_url=video_url,
            bg_color=bg_color,
            duration_seconds=duration_seconds,
        ):
            logger.info("trigger_fcm", from_user=str(current_user.user_id), to_user=str(partner_id))
            return TriggerResponse(delivered=True, method="fcm")

    logger.info("trigger_offline", from_user=str(current_user.user_id), to_user=str(partner_id))
    return TriggerResponse(delivered=False, method="offline")
