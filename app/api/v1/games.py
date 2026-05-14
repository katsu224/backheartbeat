import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.cadaver_game import CadaverGame
from app.models.user import User
from app.repositories.couple_repo import CoupleRepository
from app.services.connection_manager import manager

logger = structlog.get_logger()
router = APIRouter(prefix="/games", tags=["games"])

CADAVER_DIR = Path("/app/data/cadaver")
MAX_IMAGE_BYTES = 15 * 1024 * 1024


def _base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", "https")
    host  = request.headers.get("x-forwarded-host", "") or request.headers.get("host", "")
    return f"{proto}://{host}" if host else str(request.base_url).rstrip("/")


def _game_dict(game: CadaverGame, base: str) -> dict:
    gid = str(game.id)
    return {
        "id": gid,
        "player_a_id": str(game.player_a_id),
        "player_b_id": str(game.player_b_id) if game.player_b_id else None,
        "has_joined":  game.player_b_id is not None,
        "has_head":    game.head_path is not None,
        "has_body":    game.body_path is not None,
        "is_complete": game.is_complete,
        "head_url":  f"{base}/api/v1/games/cadaver/{gid}/head"  if game.head_path else None,
        "body_url":  f"{base}/api/v1/games/cadaver/{gid}/body"  if game.body_path else None,
        "guide_url": f"{base}/api/v1/games/cadaver/{gid}/guide" if game.head_path else None,
        "created_at": game.created_at.isoformat(),
    }


async def _load_game(db: AsyncSession, game_id: uuid.UUID, current_user: User) -> CadaverGame:
    result = await db.execute(select(CadaverGame).where(CadaverGame.id == game_id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(404, {"error": "NOT_FOUND"})
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple or couple.couple_id != game.couple_id:
        raise HTTPException(403, {"error": "FORBIDDEN"})
    return game


async def _partner_id(couple, user_id: uuid.UUID) -> uuid.UUID | None:
    return couple.user_b_id if couple.user_a_id == user_id else couple.user_a_id


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/cadaver/create", status_code=status.HTTP_201_CREATED)
async def create_cadaver_game(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple:
        raise HTTPException(400, {"error": "NOT_IN_COUPLE"})

    game = CadaverGame(couple_id=couple.couple_id, player_a_id=current_user.user_id)
    db.add(game)
    await db.flush()
    await db.refresh(game)
    await db.commit()

    pid = await _partner_id(couple, current_user.user_id)
    if pid:
        await manager.send_to_user(pid, {
            "type": "cadaver_invite",
            "game_id": str(game.id),
            "from_name": current_user.name,
        })

    logger.info("cadaver_created", game_id=str(game.id))
    return {"game_id": str(game.id)}


@router.post("/cadaver/{game_id}/join")
async def join_cadaver_game(
    game_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_game(db, game_id, current_user)

    if game.player_a_id == current_user.user_id:
        raise HTTPException(403, {"error": "PLAYER_A_CANNOT_JOIN_OWN_GAME"})
    if game.player_b_id is not None:
        raise HTTPException(400, {"error": "GAME_ALREADY_JOINED"})
    if game.is_complete:
        raise HTTPException(400, {"error": "GAME_ALREADY_COMPLETE"})

    game.player_b_id = current_user.user_id
    await db.commit()

    await manager.send_to_user(game.player_a_id, {
        "type": "cadaver_joined",
        "game_id": str(game_id),
        "from_name": current_user.name,
    })

    logger.info("cadaver_joined", game_id=str(game_id), player_b=str(current_user.user_id))
    return _game_dict(game, _base_url(request))


@router.get("/cadaver/{game_id}")
async def get_cadaver_game(
    game_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_game(db, game_id, current_user)
    return _game_dict(game, _base_url(request))


@router.post("/cadaver/{game_id}/head")
async def submit_head(
    game_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_game(db, game_id, current_user)

    if game.player_a_id != current_user.user_id:
        raise HTTPException(403, {"error": "ONLY_PLAYER_A_CAN_SUBMIT_HEAD"})
    if game.player_b_id is None:
        raise HTTPException(400, {"error": "WAITING_FOR_PLAYER_B_TO_JOIN"})
    if game.head_path:
        raise HTTPException(400, {"error": "HEAD_ALREADY_SUBMITTED"})

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(400, {"error": "FILE_TOO_LARGE"})

    CADAVER_DIR.mkdir(parents=True, exist_ok=True)
    head_path = CADAVER_DIR / f"{game_id}_head.png"
    head_path.write_bytes(content)
    game.head_path = str(head_path)
    await db.commit()

    base = _base_url(request)
    await manager.send_to_user(game.player_b_id, {
        "type": "cadaver_head_ready",
        "game_id": str(game_id),
        "guide_url": f"{base}/api/v1/games/cadaver/{game_id}/guide",
    })

    logger.info("cadaver_head_submitted", game_id=str(game_id))
    return _game_dict(game, base)


@router.post("/cadaver/{game_id}/body")
async def submit_body(
    game_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    game = await _load_game(db, game_id, current_user)

    if game.player_b_id is None or game.player_b_id != current_user.user_id:
        raise HTTPException(403, {"error": "ONLY_PLAYER_B_CAN_SUBMIT_BODY"})
    if not game.head_path:
        raise HTTPException(400, {"error": "HEAD_NOT_SUBMITTED_YET"})
    if game.body_path:
        raise HTTPException(400, {"error": "BODY_ALREADY_SUBMITTED"})

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(400, {"error": "FILE_TOO_LARGE"})

    CADAVER_DIR.mkdir(parents=True, exist_ok=True)
    body_path = CADAVER_DIR / f"{game_id}_body.png"
    body_path.write_bytes(content)
    game.body_path = str(body_path)
    game.is_complete = True
    await db.commit()

    base = _base_url(request)
    head_url = f"{base}/api/v1/games/cadaver/{game_id}/head"
    body_url = f"{base}/api/v1/games/cadaver/{game_id}/body"
    msg = {"type": "cadaver_complete", "game_id": str(game_id),
           "head_url": head_url, "body_url": body_url}
    await manager.send_to_user(game.player_a_id, msg)
    await manager.send_to_user(current_user.user_id, msg)

    logger.info("cadaver_complete", game_id=str(game_id))
    return _game_dict(game, base)


@router.get("/cadaver/{game_id}/head")
async def serve_head(game_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CadaverGame).where(CadaverGame.id == game_id))
    game = result.scalar_one_or_none()
    if not game or not game.head_path or not Path(game.head_path).exists():
        raise HTTPException(404, {"error": "NOT_FOUND"})
    return FileResponse(game.head_path, media_type="image/png")


@router.get("/cadaver/{game_id}/body")
async def serve_body(game_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CadaverGame).where(CadaverGame.id == game_id))
    game = result.scalar_one_or_none()
    if not game or not game.body_path or not Path(game.body_path).exists():
        raise HTTPException(404, {"error": "NOT_FOUND"})
    return FileResponse(game.body_path, media_type="image/png")


@router.get("/cadaver/{game_id}/guide")
async def serve_guide(game_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Serve the head image as a guide for Player B (client crops the bottom strip)."""
    result = await db.execute(select(CadaverGame).where(CadaverGame.id == game_id))
    game = result.scalar_one_or_none()
    if not game or not game.head_path or not Path(game.head_path).exists():
        raise HTTPException(404, {"error": "NOT_FOUND"})
    return FileResponse(game.head_path, media_type="image/png")
