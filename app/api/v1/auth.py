from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.repositories.couple_repo import CoupleRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    JoinCoupleRequest,
    JoinCoupleResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RefreshFCMRequest,
    RegisterRequest,
    RegisterResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await AuthService(db).register(body.username, body.name, body.password)
    except ValueError as exc:
        if str(exc) == "USERNAME_TAKEN":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "USERNAME_TAKEN", "message": "Ese nombre de usuario ya existe"},
            )
        raise


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await AuthService(db).login(body.username, body.password)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_CREDENTIALS", "message": "Usuario o contraseña incorrectos"},
        )


@router.post("/join-couple", response_model=JoinCoupleResponse)
async def join_couple(
    body: JoinCoupleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await AuthService(db).join_couple(current_user.user_id, body.pairing_code)
    except ValueError as exc:
        messages = {
            "INVALID_PAIRING_CODE": "Código inválido o ya usado",
            "CANNOT_JOIN_OWN_CODE": "No puedes usar tu propio código",
        }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": str(exc), "message": messages.get(str(exc), str(exc))},
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
    pairing_code: str | None = None
    is_paired = False

    if couple and couple.is_complete:
        is_paired = True
        couple_id = str(couple.couple_id)
        partner_id = (
            couple.user_b_id
            if couple.user_a_id == current_user.user_id
            else couple.user_a_id
        )
        if partner_id:
            partner = await UserRepository(db).get_by_id(partner_id)
            if partner:
                partner_name = partner.name
    else:
        pending = await couple_repo.get_pending_by_user_id(current_user.user_id)
        if pending:
            pairing_code = pending.pairing_code

    return MeResponse(
        user_id=str(current_user.user_id),
        username=current_user.username,
        name=current_user.name,
        couple_id=couple_id,
        partner_name=partner_name,
        is_paired=is_paired,
        pairing_code=pairing_code,
    )
