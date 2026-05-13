from pydantic import BaseModel, Field


class TriggerBody(BaseModel):
    button_id: str | None = None


class TriggerResponse(BaseModel):
    delivered: bool
    method: str


class ButtonCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=100, examples=["Te extraño 💭"])


class ButtonUpdate(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)


class ButtonResponse(BaseModel):
    button_id: str
    label: str


class ButtonListResponse(BaseModel):
    buttons: list[ButtonResponse]
