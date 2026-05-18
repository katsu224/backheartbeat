import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.scheduled_signal import ScheduledSignal
from app.models.signal import Signal
from app.models.user import User
from app.repositories.button_repo import ButtonRepository
from app.repositories.couple_repo import CoupleRepository
from app.repositories.user_repo import UserRepository
from app.services.connection_manager import manager
from app.services.fcm_service import send_fcm_notification

logger = structlog.get_logger()


async def _seconds_until_next() -> float:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduledSignal.scheduled_at)
            .where(ScheduledSignal.is_sent.is_(False))
            .order_by(ScheduledSignal.scheduled_at)
            .limit(1)
        )
        next_at = result.scalar_one_or_none()
    if next_at is None:
        return 60.0
    if next_at.tzinfo is None:
        next_at = next_at.replace(tzinfo=timezone.utc)
    return max(0.0, min((next_at - datetime.now(timezone.utc)).total_seconds(), 60.0))


async def scheduled_signals_worker() -> None:
    while True:
        try:
            await asyncio.sleep(await _seconds_until_next())
            await _process_due()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("scheduler_error", error=str(exc))


async def _process_due() -> None:
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(ScheduledSignal).where(
                ScheduledSignal.is_sent.is_(False),
                ScheduledSignal.scheduled_at <= now,
            )
        )
        due = result.scalars().all()
        if not due:
            return

        for sig in due:
            try:
                await _fire(db, sig)
                sig.is_sent = True
            except Exception as exc:
                logger.error("scheduler_fire_error", signal_id=str(sig.id), error=str(exc))

        await db.commit()


async def _fire(db, sig: ScheduledSignal) -> None:
    user_r = await db.execute(select(User).where(User.user_id == sig.user_id))
    sender = user_r.scalar_one_or_none()
    if not sender:
        return

    couple = await CoupleRepository(db).get_by_user_id(sig.user_id)
    if not couple:
        return

    partner_id = couple.user_b_id if couple.user_a_id == sig.user_id else couple.user_a_id
    if not partner_id:
        return

    button_label = sig.button_label or ""
    button_type  = sig.button_type
    video_url    = ""
    bg_color     = ""

    if sig.button_id:
        btn = await ButtonRepository(db).get_by_id(sig.button_id)
        if btn:
            button_label = btn.label or button_label
            button_type  = btn.button_type
            bg_color     = btn.bg_color  or ""
            if btn.video_url:
                if btn.video_url.startswith("http"):
                    video_url = btn.video_url
                else:
                    video_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}{btn.video_url}"

    # Persist to signal history
    db.add(Signal(
        sender_id=sig.user_id,
        receiver_id=partner_id,
        button_label=button_label or None,
        button_type=button_type,
        bg_color=bg_color or None,
        media_url=video_url or None,
    ))
    await db.flush()

    payload = {
        "type": "incoming_trigger",
        "from_name": sender.name,
        "button_label": button_label,
        "video_url": video_url,
        "bg_color": bg_color,
        "duration_seconds": 0,
        "button_type": button_type,
        "message": button_label or "Tu pareja te envió una señal ❤️",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if await manager.send_to_user(partner_id, payload):
        logger.info("scheduler_sent_ws", signal_id=str(sig.id))
        return

    partner = await UserRepository(db).get_by_id(partner_id)
    if partner and partner.fcm_token:
        await send_fcm_notification(
            partner.fcm_token,
            sender.name,
            button_label=button_label,
            video_url=video_url,
            bg_color=bg_color,
            duration_seconds=0,
            button_type=button_type,
        )
        logger.info("scheduler_sent_fcm", signal_id=str(sig.id))
