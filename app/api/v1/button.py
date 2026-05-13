import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.button_repo import ButtonRepository
from app.repositories.couple_repo import CoupleRepository
from app.schemas.trigger import ButtonCreate, ButtonListResponse, ButtonResponse, ButtonUpdate

router = APIRouter(prefix="/button", tags=["button"])

_MAX_BUTTONS = 10


def _to_response(b) -> ButtonResponse:
    return ButtonResponse(
        button_id=str(b.button_id),
        label=b.label,
        video_url=b.video_url,
        bg_color=b.bg_color,
        button_type=b.button_type,
    )


async def _get_couple_or_raise(db, user_id):
    couple = await CoupleRepository(db).get_by_user_id(user_id)
    if not couple:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "NOT_IN_COUPLE", "message": "No estás en una pareja"},
        )
    return couple


async def _get_own_button_or_raise(db, button_id: uuid.UUID, user_id: uuid.UUID):
    button = await ButtonRepository(db).get_by_id(button_id)
    if not button:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Botón no encontrado"})
    if button.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "No es tu botón"})
    return button


@router.post("/create", response_model=ButtonResponse, status_code=status.HTTP_201_CREATED)
async def create_button(
    body: ButtonCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple = await _get_couple_or_raise(db, current_user.user_id)

    existing = await ButtonRepository(db).list_by_couple(couple.couple_id)
    mine = [b for b in existing if b.owner_user_id == current_user.user_id]
    if len(mine) >= _MAX_BUTTONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "MAX_BUTTONS", "message": f"Máximo {_MAX_BUTTONS} botones"},
        )

    button = await ButtonRepository(db).create(
        couple_id=couple.couple_id,
        owner_user_id=current_user.user_id,
        label=body.label,
        button_type=body.button_type,
    )
    await db.commit()
    return _to_response(button)


@router.get("/list", response_model=ButtonListResponse)
async def list_buttons(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple:
        return ButtonListResponse(buttons=[])

    buttons = await ButtonRepository(db).list_by_couple(couple.couple_id)
    mine = [b for b in buttons if b.owner_user_id == current_user.user_id]
    return ButtonListResponse(buttons=[_to_response(b) for b in mine])


@router.put("/{button_id}", response_model=ButtonResponse)
async def update_button(
    button_id: uuid.UUID,
    body: ButtonUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    button = await _get_own_button_or_raise(db, button_id, current_user.user_id)
    if body.label is not None:
        button.label = body.label
    if body.bg_color is not None:
        button.bg_color = body.bg_color if body.bg_color != "" else None
    if body.video_url is not None:
        button.video_url = body.video_url if body.video_url != "" else None
    await db.commit()
    await db.refresh(button)
    return _to_response(button)


@router.delete("/{button_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_button(
    button_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_own_button_or_raise(db, button_id, current_user.user_id)
    await ButtonRepository(db).delete(button_id)
    await db.commit()
