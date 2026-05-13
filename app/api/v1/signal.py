from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.signal import Signal
from app.models.user import User
from app.schemas.signal import SignalHistoryItem, SignalHistoryResponse

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/history", response_model=SignalHistoryResponse)
async def get_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Signal)
        .where(
            or_(
                Signal.sender_id == current_user.user_id,
                Signal.receiver_id == current_user.user_id,
            )
        )
        .order_by(Signal.created_at.desc())
        .limit(100)
    )
    signals = result.scalars().all()

    partner_ids = {
        (s.receiver_id if s.sender_id == current_user.user_id else s.sender_id)
        for s in signals
    }

    name_map: dict = {}
    if partner_ids:
        users_result = await db.execute(
            select(User).where(User.user_id.in_(partner_ids))
        )
        name_map = {u.user_id: u.name for u in users_result.scalars().all()}

    items = []
    for s in signals:
        is_sent = s.sender_id == current_user.user_id
        partner_id = s.receiver_id if is_sent else s.sender_id
        items.append(
            SignalHistoryItem(
                id=str(s.id),
                direction="sent" if is_sent else "received",
                other_name=name_map.get(partner_id, "?"),
                button_label=s.button_label or "",
                button_type=s.button_type,
                bg_color=s.bg_color or "",
                created_at=s.created_at.isoformat(),
            )
        )

    return SignalHistoryResponse(signals=items)
