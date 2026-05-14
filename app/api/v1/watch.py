import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.models.watch_clip import WatchClip
from app.models.watch_room import WatchRoom
from app.repositories.couple_repo import CoupleRepository
from app.repositories.user_repo import UserRepository
from app.schemas.watch import AddClipRequest, ClipItem, ClipsResponse, CreateRoomRequest, RoomListItem, RoomResponse, RoomsListResponse

router = APIRouter(prefix="/watch", tags=["watch"])

_YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"


@router.get("/search")
async def search_youtube(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
):
    if not settings.YOUTUBE_API_KEY:
        raise HTTPException(status_code=503, detail={"error": "YOUTUBE_API_NOT_CONFIGURED"})

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_YT_SEARCH, params={
            "part": "snippet",
            "q": q,
            "type": "video",
            "videoEmbeddable": "true",
            "videoSyndicated": "true",
            "maxResults": 15,
            "key": settings.YOUTUBE_API_KEY,
        })

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail={"error": "YOUTUBE_API_ERROR"})

    items = resp.json().get("items", [])
    return {
        "results": [
            {
                "video_id": i["id"]["videoId"],
                "title": i["snippet"]["title"],
                "channel": i["snippet"]["channelTitle"],
                "thumbnail": i["snippet"]["thumbnails"].get("medium", {}).get("url", ""),
            }
            for i in items
            if i.get("id", {}).get("videoId")
        ]
    }


async def _get_room_or_raise(db: AsyncSession, room_id: uuid.UUID) -> WatchRoom:
    result = await db.execute(select(WatchRoom).where(WatchRoom.room_id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail={"error": "ROOM_NOT_FOUND"})
    return room


@router.get("/rooms", response_model=RoomsListResponse)
async def list_rooms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple:
        return RoomsListResponse(rooms=[])

    result = await db.execute(
        select(WatchRoom)
        .where(WatchRoom.couple_id == couple.couple_id, WatchRoom.is_active.is_(True))
        .order_by(WatchRoom.created_at.desc())
        .limit(20)
    )
    rooms = result.scalars().all()

    host_ids = {r.host_user_id for r in rooms}
    name_map: dict = {}
    if host_ids:
        users_result = await db.execute(select(User).where(User.user_id.in_(host_ids)))
        name_map = {u.user_id: u.name for u in users_result.scalars().all()}

    return RoomsListResponse(rooms=[
        RoomListItem(
            room_id=str(r.room_id),
            video_id=r.video_id,
            video_title=r.video_title,
            host_name=name_map.get(r.host_user_id, "?"),
            is_active=r.is_active,
            created_at=r.created_at.isoformat(),
        )
        for r in rooms
    ])


@router.post("/create", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    body: CreateRoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple:
        raise HTTPException(status_code=400, detail={"error": "NOT_IN_COUPLE"})

    room = WatchRoom(
        couple_id=couple.couple_id,
        host_user_id=current_user.user_id,
        video_id=body.video_id,
        video_title=body.video_title,
    )
    db.add(room)
    await db.flush()
    await db.refresh(room)
    await db.commit()

    return RoomResponse(
        room_id=str(room.room_id),
        video_id=room.video_id,
        video_title=room.video_title,
        host_user_id=str(room.host_user_id),
        is_active=room.is_active,
    )


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = await _get_room_or_raise(db, room_id)
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple or couple.couple_id != room.couple_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN"})
    return RoomResponse(
        room_id=str(room.room_id),
        video_id=room.video_id,
        video_title=room.video_title,
        host_user_id=str(room.host_user_id),
        is_active=room.is_active,
    )


@router.post("/{room_id}/clip", response_model=ClipItem, status_code=status.HTTP_201_CREATED)
async def add_clip(
    room_id: uuid.UUID,
    body: AddClipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = await _get_room_or_raise(db, room_id)
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple or couple.couple_id != room.couple_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN"})

    clip = WatchClip(
        room_id=room.room_id,
        user_id=current_user.user_id,
        position_seconds=body.position_seconds,
        end_seconds=body.end_seconds,
        label=body.label,
    )
    db.add(clip)
    await db.flush()
    await db.refresh(clip)
    await db.commit()

    return ClipItem(
        clip_id=str(clip.clip_id),
        user_id=str(clip.user_id),
        user_name=current_user.name,
        position_seconds=clip.position_seconds,
        end_seconds=clip.end_seconds,
        label=clip.label,
        created_at=clip.created_at.isoformat(),
    )


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = await _get_room_or_raise(db, room_id)
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple or couple.couple_id != room.couple_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN"})
    await db.delete(room)
    await db.commit()


@router.get("/{room_id}/clips", response_model=ClipsResponse)
async def list_clips(
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = await _get_room_or_raise(db, room_id)
    couple = await CoupleRepository(db).get_by_user_id(current_user.user_id)
    if not couple or couple.couple_id != room.couple_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN"})

    result = await db.execute(
        select(WatchClip)
        .where(WatchClip.room_id == room_id)
        .order_by(WatchClip.position_seconds)
    )
    clips = result.scalars().all()

    user_ids = {c.user_id for c in clips}
    name_map: dict = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.user_id.in_(user_ids)))
        name_map = {u.user_id: u.name for u in users_result.scalars().all()}

    return ClipsResponse(clips=[
        ClipItem(
            clip_id=str(c.clip_id),
            user_id=str(c.user_id),
            user_name=name_map.get(c.user_id, "?"),
            position_seconds=c.position_seconds,
            end_seconds=c.end_seconds,
            label=c.label,
            created_at=c.created_at.isoformat(),
        )
        for c in clips
    ])
