from pydantic import BaseModel, Field


class TriggerResponse(BaseModel):
    delivered: bool
    method: str


class ButtonCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=100, examples=["Abrazar a mi gruñona"])


class ButtonResponse(BaseModel):
    button_id: str
    label: str


class ButtonListResponse(BaseModel):
    buttons: list[ButtonResponse]
