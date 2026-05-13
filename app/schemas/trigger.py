from pydantic import BaseModel, Field


class TriggerBody(BaseModel):
    button_id: str | None = None
    duration_seconds: int = 0


class TriggerResponse(BaseModel):
    delivered: bool
    method: str


class ButtonCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=100, examples=["Te extraño 💭"])
    button_type: str = "text"


class ButtonUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=100)
    bg_color: str | None = None
    video_url: str | None = None


class ButtonResponse(BaseModel):
    button_id: str
    label: str
    video_url: str | None = None
    bg_color: str | None = None
    button_type: str = "text"


class ButtonListResponse(BaseModel):
    buttons: list[ButtonResponse]
