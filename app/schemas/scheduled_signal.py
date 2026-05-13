from datetime import datetime

from pydantic import BaseModel


class CreateScheduledSignalRequest(BaseModel):
    button_id: str | None = None
    button_label: str | None = None
    scheduled_at: datetime  # ISO-8601 with timezone


class ScheduledSignalItem(BaseModel):
    id: str
    button_id: str | None
    button_label: str | None
    button_type: str
    scheduled_at: str
    is_sent: bool
    created_at: str


class ScheduledSignalsResponse(BaseModel):
    signals: list[ScheduledSignalItem]
