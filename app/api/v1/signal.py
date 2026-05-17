from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.couple import Couple
from app.models.signal import Signal
from app.models.user import User
from app.schemas.signal import SignalHistoryItem, SignalHistoryResponse

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/history", response_model=SignalHistoryResponse)
async def get_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Resolve the current partner from the active couple
    couple_result = await db.execute(
        select(Couple).where(
            and_(
                or_(
                    Couple.user_a_id == current_user.user_id,
                    Couple.user_b_id == current_user.user_id,
                ),
                Couple.is_complete == True,
            )
        )
    )
    couple = couple_result.scalars().first()

    if couple is None:
        return SignalHistoryResponse(signals=[])

    partner_id = (
        couple.user_b_id
        if couple.user_a_id == current_user.user_id
        else couple.user_a_id
    )

    result = await db.execute(
        select(Signal)
        .where(
            or_(
                and_(
                    Signal.sender_id == current_user.user_id,
                    Signal.receiver_id == partner_id,
                ),
                and_(
                    Signal.sender_id == partner_id,
                    Signal.receiver_id == current_user.user_id,
                ),
            )
        )
        .order_by(Signal.created_at.desc())
        .limit(100)
    )
    signals = result.scalars().all()

    partner_name_result = await db.execute(
        select(User.name).where(User.user_id == partner_id)
    )
    partner_name = partner_name_result.scalar() or "?"

    items = []
    for s in signals:
        is_sent = s.sender_id == current_user.user_id
        items.append(
            SignalHistoryItem(
                id=str(s.id),
                direction="sent" if is_sent else "received",
                other_name=partner_name,
                button_label=s.button_label or "",
                button_type=s.button_type,
                bg_color=s.bg_color or "",
                media_url=s.media_url,
                video_reply_url=s.video_reply_url,
                created_at=s.created_at.isoformat(),
            )
        )

    return SignalHistoryResponse(signals=items)
