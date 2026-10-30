from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator


class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=8, max_length=128)
    is_active: bool = True


class UserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=254)
    is_active: bool | None = None

    @model_validator(mode="after")
    def check_fields(self):
        if not self.model_fields_set:
            raise ValueError("Нужно передать хотя бы одно поле")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Поля пользователя не могут быть null")
        return self


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    is_active: bool
    created_at: datetime


class Login(BaseModel):
    email: EmailStr
    password: SecretStr
