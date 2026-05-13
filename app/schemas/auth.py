from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$",
                          examples=["ana_garcia"])
    name: str = Field(..., min_length=1, max_length=50, examples=["Ana"])
    password: str = Field(..., min_length=6, max_length=100)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class RefreshFCMRequest(BaseModel):
    fcm_token: str = Field(..., min_length=1)


class RegisterResponse(BaseModel):
    user_id: str
    auth_token: str
    pairing_code: str
    name: str
    username: str


class LoginResponse(BaseModel):
    user_id: str
    auth_token: str
    name: str
    username: str
    is_paired: bool
    pairing_code: str | None


class JoinCoupleRequest(BaseModel):
    pairing_code: str = Field(..., min_length=6, max_length=6)


class JoinCoupleResponse(BaseModel):
    couple_id: str
    partner_name: str


class MeResponse(BaseModel):
    user_id: str
    username: str
    name: str
    couple_id: str | None
    partner_name: str | None
    is_paired: bool
    pairing_code: str | None
