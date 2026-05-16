from datetime import date

from pydantic import BaseModel, Field


class RequestPairingBody(BaseModel):
    pairing_code: str = Field(..., min_length=6, max_length=6)


class RequestPairingResponse(BaseModel):
    request_id: str
    status: str


class AcceptRejectResponse(BaseModel):
    status: str
    partner_name: str | None = None
    couple_id: str | None = None


class UnpairResponse(BaseModel):
    status: str
    new_pairing_code: str


class CoupleStatsResponse(BaseModel):
    days_together: int
    paired_since: date
