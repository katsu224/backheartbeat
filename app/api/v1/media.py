import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.button_repo import ButtonRepository

logger = structlog.get_logger()
router = APIRouter(prefix="/media", tags=["media"])

VIDEOS_DIR = Path("/app/data/videos")
IMAGES_DIR = Path("/app/data/images")
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
