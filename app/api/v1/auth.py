from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.repositories.couple_repo import CoupleRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    CreateUserRequest,
    CreateUserResponse,
    JoinCoupleRequest,
    JoinCoupleResponse,
    MeResponse,
    RefreshFCMRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/create-user", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def create_user(
    request: Request,
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
):
    return await AuthService(db).create_user(body.name)


@router.post("/join-couple", response_model=JoinCoupleResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def join_couple(
    request: Request,
    body: JoinCoupleRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await AuthService(db).join_couple(body.name, body.pairing_code)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_PAIRING_CODE", "message": str(exc)},
        )


@router.post("/refresh-fcm")
async def refresh_fcm(
    body: RefreshFCMRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await UserRepository(db).update_fcm_token(current_user.user_id, body.fcm_token)
    await db.commit()
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple_repo = CoupleRepository(db)
    couple = await couple_repo.get_by_user_id(current_user.user_id)

    partner_name: str | None = None
    couple_id: str | None = None
    is_paired = False

    if couple:
        couple_id = str(couple.couple_id)
        is_paired = couple.is_complete
        partner_id = (
            couple.user_b_id
            if couple.user_a_id == current_user.user_id
            else couple.user_a_id
        )
        if partner_id:
            partner = await UserRepository(db).get_by_id(partner_id)
            if partner:
                partner_name = partner.name

    return MeResponse(
        user_id=str(current_user.user_id),
        name=current_user.name,
        couple_id=couple_id,
        partner_name=partner_name,
        is_paired=is_paired,
    )
