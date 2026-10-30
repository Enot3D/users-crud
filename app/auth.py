from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import get_session
from app.models import User
from app.schemas import Login

router = APIRouter(prefix="/auth", tags=["Авторизация"])
passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
dummy_hash = passwords.hash("dummy-password")


async def hash_password(password: str) -> str:
    return await run_in_threadpool(passwords.hash, password)


def unauthorized():
    return HTTPException(
        401, "Неверные данные или токен", headers={"WWW-Authenticate": "Bearer"}
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise unauthorized()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise unauthorized() from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/login")
async def login(data: Login, session: Annotated[AsyncSession, Depends(get_session)]):
    user = await session.scalar(
        select(User).where(User.email == str(data.email).lower())
    )
    stored = user.password_hash if user and user.password_hash else dummy_hash
    valid = await run_in_threadpool(
        passwords.verify, data.password.get_secret_value(), stored
    )
    if not valid or user is None or not user.password_hash or not user.is_active:
        raise unauthorized()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_ttl_minutes),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}
