from datetime import date

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$",
                          examples=["ana_garcia"])
    name: str = Field(..., min_length=1, max_length=50, examples=["Ana"])
    password: str = Field(..., min_length=6, max_length=100)


class UpdateMeRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    anniversary_date: date | None = None


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class RefreshFCMRequest(BaseModel):
    fcm_token: str = Field(..., min_length=1)


class RegisterResponse(BaseModel):
    user_id: str
    auth_token: str  # alias of access_token, kept for backward compatibility
    access_token: str
    refresh_token: str
    access_expires_in: int  # seconds until access_token expires
    pairing_code: str
    name: str
    username: str


class LoginResponse(BaseModel):
    user_id: str
    auth_token: str  # alias of access_token, kept for backward compatibility
    access_token: str
    refresh_token: str
    access_expires_in: int
    name: str
    username: str
    is_paired: bool
    pairing_code: str | None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    access_expires_in: int


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None)


class JoinCoupleRequest(BaseModel):
    # Range accepts both legacy 6-char codes and new 8-char codes during transition.
    pairing_code: str = Field(..., min_length=6, max_length=8)


class JoinCoupleResponse(BaseModel):
    couple_id: str
    partner_name: str


class PendingRequestInfo(BaseModel):
    request_id: str
    from_name: str
    from_username: str


class MeResponse(BaseModel):
    user_id: str
    username: str
    name: str
    avatar_url: str | None = None
    anniversary_date: date | None = None
    couple_id: str | None
    partner_name: str | None
    partner_user_id: str | None = None
    partner_avatar_url: str | None = None
    is_paired: bool
    pairing_code: str | None
    pending_request: PendingRequestInfo | None = None
