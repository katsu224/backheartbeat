from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.button_repo import ButtonRepository
from app.repositories.couple_repo import CoupleRepository
from app.schemas.trigger import ButtonCreate, ButtonListResponse, ButtonResponse

router = APIRouter(prefix="/button", tags=["button"])


@router.post("/create", response_model=ButtonResponse, status_code=status.HTTP_201_CREATED)
async def create_button(
    body: ButtonCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "NOT_IN_COUPLE", "message": "No estás en una pareja"},
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
    return ButtonListResponse(
        buttons=[ButtonResponse(button_id=str(b.button_id), label=b.label) for b in buttons]
    )
