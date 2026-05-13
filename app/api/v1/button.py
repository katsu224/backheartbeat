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
    )
    await db.commit()
    return ButtonResponse(button_id=str(button.button_id), label=button.label)


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
    return ButtonListResponse(
        buttons=[ButtonResponse(button_id=str(b.button_id), label=b.label) for b in mine]
    )


@router.put("/{button_id}", response_model=ButtonResponse)
async def update_button(
    button_id: uuid.UUID,
    body: ButtonUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_own_button_or_raise(db, button_id, current_user.user_id)
    updated = await ButtonRepository(db).update(button_id, body.label)
    await db.commit()
    return ButtonResponse(button_id=str(updated.button_id), label=updated.label)


@router.delete("/{button_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_button(
    button_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_own_button_or_raise(db, button_id, current_user.user_id)
    await ButtonRepository(db).delete(button_id)
    await db.commit()
