import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.db.session import get_db
from app.models.signal import Signal
from app.models.user import User
from app.repositories.button_repo import ButtonRepository
from app.repositories.couple_repo import CoupleRepository
from app.repositories.user_media_repo import UserMediaRepository
from app.repositories.user_repo import UserRepository
from app.services.connection_manager import manager
from app.services.fcm_service import send_fcm_notification

MEDIA_CACHE_HEADERS = {"Cache-Control": "private, max-age=86400"}
SELFIE_QUOTA = 100
VOICE_QUOTA = 100


async def _partner_id_for(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    couple = await CoupleRepository(db).get_by_user_id(user_id)
    if not couple:
        return None
    return couple.user_b_id if couple.user_a_id == user_id else couple.user_a_id


def _forbid() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "FORBIDDEN"})


def _file_etag(path: Path) -> str:
    stat = path.stat()
    return f'W/"{int(stat.st_mtime)}-{stat.st_size}"'


def _cached_file_response(request: Request, path: Path, media_type: str) -> Response:
    etag = _file_etag(path)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={**MEDIA_CACHE_HEADERS, "ETag": etag})
    return FileResponse(
        str(path),
        media_type=media_type,
        headers={**MEDIA_CACHE_HEADERS, "ETag": etag},
    )

SELFIES_DIR  = Path("/app/data/selfies")
VOICES_DIR   = Path("/app/data/voices")
AVATARS_DIR  = Path("/app/data/avatars")
ALLOWED_AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB
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
@limiter.limit("20/minute")
async def upload_video(
    request: Request,
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
@limiter.limit("120/minute")
async def serve_video(
    request: Request,
    button_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    btn = await ButtonRepository(db).get_by_id(button_id)
    if not btn or not btn.video_path:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})

    partner_id = await _partner_id_for(db, current_user.user_id)
    if btn.owner_user_id != current_user.user_id and btn.owner_user_id != partner_id:
        raise _forbid()

    path = Path(btn.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "FILE_MISSING"})

    media_type = "video/webm" if path.suffix == ".webm" else "video/mp4"
    return _cached_file_response(request, path, media_type)


@router.post("/image/{button_id}")
@limiter.limit("20/minute")
async def upload_image(
    request: Request,
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
@limiter.limit("120/minute")
async def serve_image(
    request: Request,
    button_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    btn = await ButtonRepository(db).get_by_id(button_id)
    if not btn or not btn.video_path or not btn.video_path.startswith("/app/data/images/"):
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})

    partner_id = await _partner_id_for(db, current_user.user_id)
    if btn.owner_user_id != current_user.user_id and btn.owner_user_id != partner_id:
        raise _forbid()

    path = Path(btn.video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "FILE_MISSING"})

    suffix = path.suffix.lower()
    mime_map = {".gif": "image/gif", ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".webp": "image/webp"}
    return _cached_file_response(request, path, mime_map.get(suffix, "image/gif"))


@router.post("/signal/{signal_id}/reply")
@limiter.limit("20/minute")
async def upload_signal_reply(
    request: Request,
    signal_id: uuid.UUID,
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
@limiter.limit("120/minute")
async def serve_signal_reply(
    request: Request,
    signal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    sig = result.scalar_one_or_none()
    if not sig:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    if current_user.user_id not in (sig.sender_id, sig.receiver_id):
        raise _forbid()

    for ext in ALLOWED_EXTENSIONS:
        path = REPLIES_DIR / f"{signal_id}{ext}"
        if path.exists():
            media_type = "video/webm" if ext == ".webm" else "video/mp4"
            return _cached_file_response(request, path, media_type)
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
@limiter.limit("10/minute")
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
    file_path = SELFIES_DIR / f"{selfie_id}{suffix}"
    file_path.write_bytes(content)

    media_repo = UserMediaRepository(db)
    await media_repo.record(
        user_id=current_user.user_id,
        media_type="selfie",
        file_path=str(file_path),
        size_bytes=len(content),
    )
    await media_repo.enforce_quota(current_user.user_id, "selfie", SELFIE_QUOTA)
    await db.commit()

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
@limiter.limit("120/minute")
async def serve_selfie(
    request: Request,
    selfie_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    owner_row = await UserMediaRepository(db).get_owner_by_path_prefix(
        str(SELFIES_DIR), selfie_id
    )
    if not owner_row:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})

    partner_id = await _partner_id_for(db, current_user.user_id)
    if owner_row.user_id != current_user.user_id and owner_row.user_id != partner_id:
        raise _forbid()

    path = Path(owner_row.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "FILE_MISSING"})

    mime_map = {".gif": "image/gif", ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".webp": "image/webp"}
    return _cached_file_response(request, path, mime_map.get(path.suffix.lower(), "image/jpeg"))


@router.post("/voice")
@limiter.limit("10/minute")
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
    file_path = VOICES_DIR / f"{voice_id}{suffix}"
    file_path.write_bytes(content)

    media_repo = UserMediaRepository(db)
    await media_repo.record(
        user_id=current_user.user_id,
        media_type="voice",
        file_path=str(file_path),
        size_bytes=len(content),
    )
    await media_repo.enforce_quota(current_user.user_id, "voice", VOICE_QUOTA)
    await db.commit()

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
@limiter.limit("120/minute")
async def serve_voice(
    request: Request,
    voice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    owner_row = await UserMediaRepository(db).get_owner_by_path_prefix(
        str(VOICES_DIR), voice_id
    )
    if not owner_row:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})

    partner_id = await _partner_id_for(db, current_user.user_id)
    if owner_row.user_id != current_user.user_id and owner_row.user_id != partner_id:
        raise _forbid()

    path = Path(owner_row.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "FILE_MISSING"})

    mime_map = {".m4a": "audio/mp4", ".aac": "audio/aac", ".mp3": "audio/mpeg",
                ".3gp": "audio/3gpp", ".ogg": "audio/ogg", ".opus": "audio/ogg"}
    return _cached_file_response(request, path, mime_map.get(path.suffix.lower(), "audio/mp4"))


@router.post("/avatar")
@limiter.limit("5/minute")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    suffix = Path(file.filename or "avatar.jpg").suffix.lower()
    if suffix not in ALLOWED_AVATAR_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FORMAT", "message": "Solo se aceptan JPG, PNG, WEBP"},
        )

    content = await file.read()
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=400,
            detail={"error": "FILE_TOO_LARGE", "message": "Máximo 5 MB"},
        )

    AVATARS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove old avatar file (any extension)
    user_id = current_user.user_id
    for ext in ALLOWED_AVATAR_EXTENSIONS:
        old = AVATARS_DIR / f"{user_id}{ext}"
        old.unlink(missing_ok=True)

    file_path = AVATARS_DIR / f"{user_id}{suffix}"
    file_path.write_bytes(content)

    await UserRepository(db).update_avatar_path(user_id, str(file_path))
    await db.commit()

    logger.info("avatar_uploaded", user_id=str(user_id), bytes=len(content))
    return {"avatar_url": f"/api/v1/media/avatar/{user_id}"}


@router.get("/avatar/{user_id}")
@limiter.limit("120/minute")
async def serve_avatar(
    request: Request,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user_id != current_user.user_id:
        partner_id = await _partner_id_for(db, current_user.user_id)
        if user_id != partner_id:
            raise _forbid()

    for suffix in ALLOWED_AVATAR_EXTENSIONS:
        path = AVATARS_DIR / f"{user_id}{suffix}"
        if path.exists():
            mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                        ".png": "image/png", ".webp": "image/webp"}
            etag = _file_etag(path)
            if request.headers.get("if-none-match") == etag:
                return Response(status_code=304, headers={"Cache-Control": "private, max-age=300", "ETag": etag})
            return FileResponse(
                str(path),
                media_type=mime_map.get(suffix, "image/jpeg"),
                headers={"Cache-Control": "private, max-age=300", "ETag": etag},
            )
    raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})


@router.delete("/video/{button_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_video(
    request: Request,
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
