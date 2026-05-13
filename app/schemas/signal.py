from pydantic import BaseModel


class SignalHistoryItem(BaseModel):
    id: str
    direction: str          # "sent" | "received"
    other_name: str
    button_label: str
    button_type: str
    bg_color: str
    video_reply_url: str | None = None
    created_at: str         # ISO-8601 UTC


class SignalHistoryResponse(BaseModel):
    signals: list[SignalHistoryItem]
