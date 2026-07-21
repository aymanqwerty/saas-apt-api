from pydantic import BaseModel, EmailStr, Field

from app.schemas.doctor import DoctorResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginData(BaseModel):
    token: str
    doctor: DoctorResponse
