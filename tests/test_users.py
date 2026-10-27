import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cache import get_cache
from app.database import Base, get_session
from app.main import app


@pytest.fixture
async def api(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cache = FakeRedis(decode_responses=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def session_override():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_cache] = lambda: cache
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, cache
    finally:
        app.dependency_overrides.clear()
        await cache.aclose()
        await engine.dispose()


async def test_crud_and_cache(api):
    client, cache = api
    assert (await client.get("/users")).json() == []
    response = await client.post(
        "/users", json={"name": "Иван", "email": "Ivan@example.com"}
    )
    assert response.status_code == 201
    user = response.json()
    assert user["email"] == "ivan@example.com"
    user_id = user["id"]
    assert (await client.get(f"/users/{user_id}")).json() == user
    assert (await client.get("/users")).json() == [user]
    version = await cache.get("users:version")
    assert await cache.exists(f"users:list:{version}:0:20")
    assert (await client.get("/users")).json() == [user]
    response = await client.patch(
        f"/users/{user_id}", json={"name": "Пётр", "is_active": False}
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert (await client.get("/users")).json()[0]["name"] == "Пётр"
    assert (await client.get("/users?offset=1&limit=1")).json() == []
    response = await client.delete(f"/users/{user_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert (await client.get("/users")).json() == []
    assert (await client.get(f"/users/{user_id}")).status_code == 404
    assert (
        await client.patch(f"/users/{user_id}", json={"name": "Иван"})
    ).status_code == 404
    assert (await client.delete(f"/users/{user_id}")).status_code == 404


async def test_duplicate_email_and_rollback(api):
    client, _ = api
    for name in ["Иван", "Пётр"]:
        response = await client.post(
            "/users", json={"name": name, "email": f"{name == 'Иван'}@example.com"}
        )
        assert response.status_code == 201
    response = await client.post(
        "/users", json={"name": "Олег", "email": "TRUE@example.com"}
    )
    assert response.status_code == 409
    response = await client.patch("/users/2", json={"email": "true@example.com"})
    assert response.status_code == 409
    assert (await client.get("/users/2")).json()["email"] == "false@example.com"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "email": "a@example.com"},
        {"name": "Иван", "email": "wrong"},
        {"name": "Иван", "email": "a@example.com", "unknown": 1},
    ],
)
async def test_invalid_create(api, payload):
    client, _ = api
    assert (await client.post("/users", json=payload)).status_code == 422


@pytest.mark.parametrize(
    "payload", [{}, {"name": None}, {"email": None}, {"is_active": None}, {"name": " "}]
)
async def test_invalid_update(api, payload):
    client, _ = api
    assert (await client.patch("/users/1", json=payload)).status_code == 422


async def test_redis_failure(api, monkeypatch):
    client, cache = api

    async def unavailable(*args, **kwargs):
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr(cache, "get", unavailable)
    monkeypatch.setattr(cache, "set", unavailable)
    response = await client.post(
        "/users", json={"name": "Иван", "email": "ivan@example.com"}
    )
    assert response.status_code == 201
    assert len((await client.get("/users")).json()) == 1


async def test_pagination_validation(api):
    client, _ = api
    for query in ["offset=-1", "limit=0", "limit=101"]:
        assert (await client.get(f"/users?{query}")).status_code == 422
