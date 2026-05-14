import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.signal import Signal
from app.models.user import User
from app.repositories.button_repo import ButtonRepository
from app.repositories.couple_repo import CoupleRepository
from app.services.connection_manager import manager
from app.services.fcm_service import send_fcm_notification

SELFIES_DIR = Path("/app/data/selfies")
VOICES_DIR  = Path("/app/data/voices")
ALLOWED_AUDIO_EXTENSIONS = {".m4a", ".aac", ".mp3", ".3gp", ".ogg", ".opus"}
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB

logger = structlog.get_logger()
router = APIRouter(prefix="/media", tags=["media"])

VIDEOS_DIR  = Path("/app/data/videos")
IMAGES_DIR  = Path("/app/data/images")
REPLIES_DIR = Path("/app/data/replies")
ALLOWED_EXTENSIONS = {".mp4", ".webm"}
ALLOWED_IMAGE_EXTENSIONS = {".gif", ".png", ".jpg", ".jpeg", ".webp"}
MAX_VIDEO_BYTES = 50 * 1024 * 1024   # 50 MB
MAX_IMAGE_BYTES = 10 * 1024 * 1024   # 10 MB


async def _own_button(db, button_id: uuid.UUID, user_id: uuid.UUID):
    btn = await ButtonRepository(db).get_by_id(button_id)
    if not btn:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    if btn.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN"})
    return btn


@router.post("/video/{button_id}")
async def upload_video(
    button_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    btn = await _own_button(db, button_id, current_user.user_id)

    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FORMAT", "message": "Solo se aceptan .mp4 y .webm"},
        )

    content = await file.read()
    if len(content) > MAX_VIDEO_BYTES:
        raise HTTPException(
            status_code=400,
            detail={"error": "FILE_TOO_LARGE", "message": "Máximo 50 MB"},
        )

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove old file if different extension
    if btn.video_path:
        old = Path(btn.video_path)
        if old.exists() and old != VIDEOS_DIR / f"{button_id}{suffix}":
            old.unlink(missing_ok=True)

    file_path = VIDEOS_DIR / f"{button_id}{suffix}"
    file_path.write_bytes(content)

    btn.video_path = str(file_path)
    btn.video_url = f"/api/v1/media/video/{button_id}"
    await db.commit()

    logger.info("video_uploaded", button_id=str(button_id), bytes=len(content))
    return {"video_url": btn.video_url}


@router.get("/video/{button_id}")
async def serve_video(button_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    btn = await ButtonRepository(db).get_by_id(button_id)
    if not btn or not btn.video_path:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})

    path = Path(btn.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "FILE_MISSING"})

    media_type = "video/webm" if path.suffix == ".webm" else "video/mp4"
    return FileResponse(str(path), media_type=media_type)


@router.post("/image/{button_id}")
async def upload_image(
    button_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    btn = await _own_button(db, button_id, current_user.user_id)

    suffix = Path(file.filename or "image.gif").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FORMAT", "message": "Solo se aceptan GIF, PNG, JPG, WEBP"},
        )

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=400,
            detail={"error": "FILE_TOO_LARGE", "message": "Máximo 10 MB"},
        )

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    if btn.video_path and btn.video_path.startswith("/app/data/images/"):
        old = Path(btn.video_path)
        if old.exists():
            old.unlink(missing_ok=True)

    file_path = IMAGES_DIR / f"{button_id}{suffix}"
    file_path.write_bytes(content)

    btn.video_path = str(file_path)
    btn.video_url = f"/api/v1/media/image/{button_id}"
    await db.commit()

    logger.info("image_uploaded", button_id=str(button_id), bytes=len(content))
    return {"video_url": btn.video_url}


@router.get("/image/{button_id}")
async def serve_image(button_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    btn = await ButtonRepository(db).get_by_id(button_id)
    if not btn or not btn.video_path or not btn.video_path.startswith("/app/data/images/"):
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})

    path = Path(btn.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "FILE_MISSING"})

    suffix = path.suffix.lower()
    mime_map = {".gif": "image/gif", ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".webp": "image/webp"}
    return FileResponse(str(path), media_type=mime_map.get(suffix, "image/gif"))


@router.post("/signal/{signal_id}/reply")
async def upload_signal_reply(
    signal_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    sig = result.scalar_one_or_none()
    if not sig:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    if sig.receiver_id != current_user.user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN"})

    suffix = Path(file.filename or "reply.mp4").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail={"error": "INVALID_FORMAT"})

    content = await file.read()
    if len(content) > MAX_VIDEO_BYTES:
        raise HTTPException(status_code=400, detail={"error": "FILE_TOO_LARGE"})

    REPLIES_DIR.mkdir(parents=True, exist_ok=True)
    file_path = REPLIES_DIR / f"{signal_id}{suffix}"
    file_path.write_bytes(content)

    proto = request.headers.get("x-forwarded-proto", "https")
    host  = request.headers.get("x-forwarded-host", "") or request.headers.get("host", "")
    base  = f"{proto}://{host}" if host else str(request.base_url).rstrip("/")
    reply_url = f"{base}/api/v1/media/signal/{signal_id}/reply"

    sig.video_reply_url = reply_url
    await db.commit()

    # Notify original sender
    payload = {
        "type": "signal_reply",
        "signal_id": str(signal_id),
        "from_name": current_user.name,
        "video_url": reply_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not await manager.send_to_user(sig.sender_id, payload):
        sender_r = await db.execute(select(User).where(User.user_id == sig.sender_id))
        sender = sender_r.scalar_one_or_none()
        if sender and sender.fcm_token:
            await send_fcm_notification(
                sender.fcm_token,
                current_user.name,
                button_label="📹 respondió a tu señal",
                video_url=reply_url,
                bg_color="",
                duration_seconds=0,
                button_type="video",
            )

    logger.info("signal_reply_uploaded", signal_id=str(signal_id), bytes=len(content))
    return {"video_url": reply_url}


@router.get("/signal/{signal_id}/reply")
async def serve_signal_reply(signal_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    for ext in ALLOWED_EXTENSIONS:
        path = REPLIES_DIR / f"{signal_id}{ext}"
        if path.exists():
            media_type = "video/webm" if ext == ".webm" else "video/mp4"
            return FileResponse(str(path), media_type=media_type)
    raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})


async def _get_partner_id(couple, user_id: uuid.UUID) -> uuid.UUID | None:
    if couple.user_a_id == user_id:
        return couple.user_b_id
    return couple.user_a_id


async def _send_instant_signal(
    partner_id: uuid.UUID,
    from_name: str,
    button_label: str,
    button_type: str,
    media_url: str,
    db: AsyncSession,
):
    payload = {
        "type": "incoming_trigger",
        "from_name": from_name,
        "button_label": button_label,
        "video_url": media_url,
        "bg_color": "",
        "duration_seconds": 0,
        "button_type": button_type,
    }
    if not await manager.send_to_user(partner_id, payload):
        partner_r = await db.execute(select(User).where(User.user_id == partner_id))
        partner = partner_r.scalar_one_or_none()
        if partner and partner.fcm_token:
            await send_fcm_notification(
                partner.fcm_token,
                from_name,
                button_label=button_label,
                video_url=media_url,
                bg_color="",
                duration_seconds=0,
                button_type=button_type,
            )


@router.post("/selfie")
async def upload_selfie(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple:
        raise HTTPException(status_code=400, detail={"error": "NOT_IN_COUPLE"})

    suffix = Path(file.filename or "selfie.jpg").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail={"error": "INVALID_FORMAT"})

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail={"error": "FILE_TOO_LARGE"})

    selfie_id = uuid.uuid4()
    SELFIES_DIR.mkdir(parents=True, exist_ok=True)
    (SELFIES_DIR / f"{selfie_id}{suffix}").write_bytes(content)

    proto = request.headers.get("x-forwarded-proto", "https")
    host  = request.headers.get("x-forwarded-host", "") or request.headers.get("host", "")
    base  = f"{proto}://{host}" if host else str(request.base_url).rstrip("/")
    selfie_url = f"{base}/api/v1/media/selfie/{selfie_id}"

    partner_id = await _get_partner_id(couple, current_user.user_id)
    if partner_id:
        await _send_instant_signal(partner_id, current_user.name, "📸 Selfie", "selfie", selfie_url, db)

    logger.info("selfie_uploaded", selfie_id=str(selfie_id), bytes=len(content))
    return {"selfie_url": selfie_url}


@router.get("/selfie/{selfie_id}")
async def serve_selfie(selfie_id: uuid.UUID):
    for suffix in ALLOWED_IMAGE_EXTENSIONS:
        path = SELFIES_DIR / f"{selfie_id}{suffix}"
        if path.exists():
            mime_map = {".gif": "image/gif", ".png": "image/png", ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg", ".webp": "image/webp"}
            return FileResponse(str(path), media_type=mime_map.get(suffix, "image/jpeg"))
    raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})


@router.post("/voice")
async def upload_voice(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple:
        raise HTTPException(status_code=400, detail={"error": "NOT_IN_COUPLE"})

    suffix = Path(file.filename or "voice.m4a").suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail={"error": "INVALID_FORMAT"})

    content = await file.read()
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail={"error": "FILE_TOO_LARGE"})

    voice_id = uuid.uuid4()
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    (VOICES_DIR / f"{voice_id}{suffix}").write_bytes(content)

    proto = request.headers.get("x-forwarded-proto", "https")
    host  = request.headers.get("x-forwarded-host", "") or request.headers.get("host", "")
    base  = f"{proto}://{host}" if host else str(request.base_url).rstrip("/")
    voice_url = f"{base}/api/v1/media/voice/{voice_id}"

    partner_id = await _get_partner_id(couple, current_user.user_id)
    if partner_id:
        await _send_instant_signal(partner_id, current_user.name, "🎙 Nota de voz", "voice", voice_url, db)

    logger.info("voice_uploaded", voice_id=str(voice_id), bytes=len(content))
    return {"voice_url": voice_url}


@router.get("/voice/{voice_id}")
async def serve_voice(voice_id: uuid.UUID):
    mime_map = {".m4a": "audio/mp4", ".aac": "audio/aac", ".mp3": "audio/mpeg",
                ".3gp": "audio/3gpp", ".ogg": "audio/ogg", ".opus": "audio/ogg"}
    for suffix in ALLOWED_AUDIO_EXTENSIONS:
        path = VOICES_DIR / f"{voice_id}{suffix}"
        if path.exists():
            return FileResponse(str(path), media_type=mime_map.get(suffix, "audio/mp4"))
    raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})


@router.delete("/video/{button_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    button_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    btn = await _own_button(db, button_id, current_user.user_id)

    if btn.video_path:
        Path(btn.video_path).unlink(missing_ok=True)

    btn.video_path = None
    btn.video_url = None
    await db.commit()
