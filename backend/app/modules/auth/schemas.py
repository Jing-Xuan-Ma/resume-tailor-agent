from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    email: str
    full_name: str = Field(min_length=1)
    password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def valid_email(_cls, value: str) -> str:
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Invalid email")
        return value.lower()


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def valid_email(_cls, value: str) -> str:
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Invalid email")
        return value.lower()


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    user: dict
