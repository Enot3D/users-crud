from datetime import date

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic import SecretStr

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from crud.database import session_factory
from crud.models import User

from pwdlib import PasswordHash

from starlette.concurrency import run_in_threadpool

from datetime import datetime, timedelta, timezone

import jwt

from crud.database import settings


app = FastAPI()

password_hasher = PasswordHash.recommended()

bearer = HTTPBearer(auto_error=False)

class UserCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace= True,
        extra="forbid",
    )

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)

class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    created_at: date

class UserResponse(BaseModel):
    message: str
    user: UserRead

class UserUpdate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr

class UserLogin(BaseModel):
    email: EmailStr
    password: SecretStr

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    error = HTTPException(
        status_code=401,
        detail="Недействительный токен",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise error

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise error from None

    async with session_factory() as session:
        user = await session.get(User, user_id)

        if user is None:
            raise error

        return user

@app.post("/users", status_code=201, response_model=UserResponse)
async def create_user(data: UserCreate):
    async with session_factory() as session:
        password_hash = await run_in_threadpool(
            password_hasher.hash,
            data.password.get_secret_value(),
        )

        user = User(
            name=data.name,
            email=str(data.email),
            password_hash=password_hash,
        )

        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Email уже занят",
            ) from None
        await session.refresh(user)

        return {
            "message": "Пользователь создан",
            "user": user
        }

@app.delete("/users/{users_id}", status_code=200, response_model=UserResponse)
async def delete_user(users_id: int,current_user: User = Depends(get_current_user)):
    if current_user.id != users_id:
        raise HTTPException(
            status_code=403,
            detail="Можно удалять только свою запись",
        )
    async with session_factory() as session:
        user = await session.get(User, users_id)

        if user is None:
            raise HTTPException(
                status_code=409,
                detail="Пользователь не найден"
            )

        deleted_user = UserRead.model_validate(user)

        await session.delete(user)
        await session.commit()

        return{
            "message": "Пользователь удалён",
            "user": deleted_user,
        }

@app.put("/users/{users_id}", response_model=UserResponse)
async def update_user(users_id: int, data: UserUpdate, current_user: User = Depends(get_current_user)):
    if current_user.id != users_id:
        raise HTTPException(
            status_code=403,
            detail="Можно изменять только свою запись",
        )
    async with session_factory() as session:
        user = await session.get(User, users_id)

        if user is None:
            raise HTTPException(
                status_code=409,
                detail="Пользователь не найден"
            )

        user.name = data.name
        user.email = str(data.email)

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Email занят"
            ) from None

        await session.refresh(user)

        return{
            "message": "Пользователь обновлён",
            "user": user
        }

@app.get("/users", response_model=list[UserRead])
async def get_users(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
):
    async with session_factory() as session:
        result = await session.scalars(
            select(User)
            .order_by(User.id)
            .offset(offset)
            .limit(limit)
        )
    return result.all()

@app.get("/users/{users_is}", response_model=UserRead)
async def get_user(user_id: int):
    async with session_factory() as session:
        user = await session.get(User, user_id)

        if user is None:
            raise HTTPException(
                status_code=409,
                detail="Пользователь не найден"
            )
    return user

@app.post("/auth/login")
async def login(data: UserLogin):
    async with session_factory() as session:
        user = await session.scalar(
            select(User).where(User.email == str(data.email))
        )

        if user is None or user.password_hash is None:
            raise HTTPException(
                status_code=401,
                detail="Неверный email или пароль",
            )

        password_valid = await run_in_threadpool(
            password_hasher.verify,
            data.password.get_secret_value(),
            user.password_hash,
        )

        if not password_valid:
            raise HTTPException(
                status_code=401,
                detail="Неверный email или пароль",
            )

        now = datetime.now(timezone.utc)

        token = jwt.encode(
            {
                "sub": str(user.id),
                "iat": now,
                "exp": now + timedelta(minutes=30),
            },
            settings.jwt_secret,
            algorithm="HS256",
        )

        return {
            "access_token": token,
            "token_type": "bearer",
        }
