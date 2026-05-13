from pydantic import BaseModel


class CreateRoomRequest(BaseModel):
    video_id: str
    video_title: str | None = None


class RoomResponse(BaseModel):
    room_id: str
    video_id: str
    video_title: str | None
    host_user_id: str
    is_active: bool


class RoomListItem(BaseModel):
    room_id: str
    video_id: str
    video_title: str | None
    host_name: str
    is_active: bool
    created_at: str


class RoomsListResponse(BaseModel):
    rooms: list[RoomListItem]


class AddClipRequest(BaseModel):
    position_seconds: int
    label: str | None = None


class ClipItem(BaseModel):
    clip_id: str
    user_id: str
    user_name: str
    position_seconds: int
    label: str | None
    created_at: str


class ClipsResponse(BaseModel):
    clips: list[ClipItem]
