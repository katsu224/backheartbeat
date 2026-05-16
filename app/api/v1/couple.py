import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.couple import (
    AcceptRejectResponse,
    CoupleStatsResponse,
    RequestPairingBody,
    RequestPairingResponse,
    UnpairResponse,
)
from app.services.couple_service import CoupleService

router = APIRouter(prefix="/couple", tags=["couple"])

_ERRORS = {
    "INVALID_PAIRING_CODE": (400, "Código inválido o ya usado"),
    "CANNOT_JOIN_OWN_CODE": (400, "No puedes usar tu propio código"),
    "ALREADY_PAIRED": (400, "Ya estás vinculado con alguien"),
    "INVALID_REQUEST": (400, "Solicitud inválida o ya procesada"),
    "NOT_AUTHORIZED": (403, "No tienes permiso para esta acción"),
    "PAIRING_EXPIRED": (400, "El código ya fue usado por otra persona"),
    "NOT_PAIRED": (400, "No estás vinculado con nadie"),
}


def _handle(exc: ValueError):
    code, msg = _ERRORS.get(str(exc), (400, str(exc)))
    raise HTTPException(status_code=code, detail={"error": str(exc), "message": msg})


@router.post("/request", response_model=RequestPairingResponse)
async def request_pairing(
    body: RequestPairingBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await CoupleService(db).request_pairing(current_user.user_id, body.pairing_code)
    except ValueError as exc:
        _handle(exc)


@router.post("/accept/{request_id}", response_model=AcceptRejectResponse)
async def accept_pairing(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await CoupleService(db).accept_pairing(request_id, current_user.user_id)
    except ValueError as exc:
        _handle(exc)


@router.post("/reject/{request_id}", response_model=AcceptRejectResponse)
async def reject_pairing(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await CoupleService(db).reject_pairing(request_id, current_user.user_id)
    except ValueError as exc:
        _handle(exc)


@router.get("/stats", response_model=CoupleStatsResponse)
async def couple_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await CoupleService(db).get_stats(current_user.user_id)
    except ValueError as exc:
        _handle(exc)


@router.delete("/unpair", response_model=UnpairResponse)
async def unpair(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await CoupleService(db).unpair(current_user.user_id)
    except ValueError as exc:
        _handle(exc)
