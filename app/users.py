import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import TypeAdapter, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, hash_password
from app.cache import get_cache, invalidate_users
from app.config import settings
from app.database import get_session
from app.models import User
from app.schemas import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["Пользователи"])
Session = Annotated[AsyncSession, Depends(get_session)]
Cache = Annotated[Redis, Depends(get_cache)]
user_list = TypeAdapter(list[UserRead])
logger = logging.getLogger(__name__)


async def find_user(user_id: int, session: AsyncSession) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


async def save_user(user: User, session: AsyncSession):
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Этот email уже занят") from None
    await session.refresh(user)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, session: Session, cache: Cache):
    values = data.model_dump(exclude={"password"})
    values["password_hash"] = await hash_password(data.password.get_secret_value())
    values["email"] = str(data.email).lower()
    user = User(**values)
    session.add(user)
    await save_user(user, session)
    await invalidate_users(cache)
    return user


@router.get("", response_model=list[UserRead])
async def list_users(
    session: Session,
    cache: Cache,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    key = None
    try:
        version = await cache.get("users:version") or "0"
        key = f"users:list:{version}:{offset}:{limit}"
        cached = await cache.get(key)
        if cached is not None:
            return user_list.validate_json(cached)
    except (RedisError, ValidationError):
        logger.warning("Не удалось прочитать кэш пользователей", exc_info=True)

    users = await session.scalars(
        select(User).order_by(User.id).offset(offset).limit(limit)
    )
    result = [UserRead.model_validate(user) for user in users]
    if key is not None:
        try:
            await cache.set(key, user_list.dump_json(result), ex=settings.cache_ttl)
        except RedisError:
            logger.warning("Не удалось сохранить кэш пользователей", exc_info=True)
    return result


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, session: Session):
    return await find_user(user_id, session)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int, data: UserUpdate, session: Session, cache: Cache, current: CurrentUser
):
    if current.id != user_id:
        raise HTTPException(status_code=403, detail="Можно изменять только себя")
    user = await find_user(user_id, session)
    values = data.model_dump(exclude_unset=True)
    if "email" in values:
        values["email"] = str(values["email"]).lower()
    for field, value in values.items():
        setattr(user, field, value)
    await save_user(user, session)
    await invalidate_users(cache)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int, session: Session, cache: Cache, current: CurrentUser
):
    if current.id != user_id:
        raise HTTPException(status_code=403, detail="Можно удалять только себя")
    user = await find_user(user_id, session)
    await session.delete(user)
    await session.commit()
    await invalidate_users(cache)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
