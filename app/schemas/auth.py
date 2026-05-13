from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, examples=["Ana"])


class JoinCoupleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, examples=["Luis"])
    pairing_code: str = Field(..., min_length=6, max_length=6, examples=["LUNA42"])


class RefreshFCMRequest(BaseModel):
    fcm_token: str = Field(..., min_length=1)


class CreateUserResponse(BaseModel):
    user_id: str
    auth_token: str
    pairing_code: str
    name: str


class JoinCoupleResponse(BaseModel):
    user_id: str
    auth_token: str
    couple_id: str
    name: str


class MeResponse(BaseModel):
    user_id: str
    name: str
    couple_id: str | None
    partner_name: str | None
    is_paired: bool
