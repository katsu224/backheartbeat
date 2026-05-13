import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.scheduled_signal import ScheduledSignal
from app.models.user import User
from app.repositories.button_repo import ButtonRepository
from app.schemas.scheduled_signal import (
    CreateScheduledSignalRequest,
    ScheduledSignalItem,
    ScheduledSignalsResponse,
)

router = APIRouter(prefix="/scheduled-signals", tags=["scheduled-signals"])


def _to_item(s: ScheduledSignal) -> ScheduledSignalItem:
    return ScheduledSignalItem(
        id=str(s.id),
        button_id=str(s.button_id) if s.button_id else None,
        button_label=s.button_label,
        button_type=s.button_type,
        scheduled_at=s.scheduled_at.isoformat(),
        is_sent=s.is_sent,
        created_at=s.created_at.isoformat(),
    )


@router.post("", response_model=ScheduledSignalItem, status_code=status.HTTP_201_CREATED)
async def create_scheduled_signal(
    body: CreateScheduledSignalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.scheduled_at.tzinfo is None:
        raise HTTPException(status_code=400, detail={"error": "MISSING_TIMEZONE"})
    if body.scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail={"error": "SCHEDULED_AT_PAST"})

    label = body.button_label
    btype = "text"

    if body.button_id:
        try:
            btn = await ButtonRepository(db).get_by_id(uuid.UUID(body.button_id))
            if btn and btn.owner_user_id == current_user.user_id:
                label = label or btn.label
                btype = btn.button_type
        except (ValueError, AttributeError):
            pass

    sig = ScheduledSignal(
        user_id=current_user.user_id,
        button_id=uuid.UUID(body.button_id) if body.button_id else None,
        button_label=label,
        button_type=btype,
        scheduled_at=body.scheduled_at,
    )
    db.add(sig)
    await db.flush()
    await db.refresh(sig)
    await db.commit()
    return _to_item(sig)


@router.get("", response_model=ScheduledSignalsResponse)
async def list_scheduled_signals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScheduledSignal)
        .where(
            ScheduledSignal.user_id == current_user.user_id,
            ScheduledSignal.is_sent.is_(False),
        )
        .order_by(ScheduledSignal.scheduled_at)
    )
    return ScheduledSignalsResponse(signals=[_to_item(s) for s in result.scalars().all()])


@router.delete("/{signal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_scheduled_signal(
    signal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScheduledSignal).where(
            ScheduledSignal.id == signal_id,
            ScheduledSignal.user_id == current_user.user_id,
        )
    )
    sig = result.scalar_one_or_none()
    if not sig:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    await db.delete(sig)
    await db.commit()
