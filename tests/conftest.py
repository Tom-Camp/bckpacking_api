import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool
from sqlmodel import SQLModel

import app.models  # noqa: F401  registers all table models on SQLModel.metadata

# Defaults to in-memory SQLite; CI sets this to a Postgres URL (postgresql+asyncpg://...).
# Never point it at a database you care about: every test drops and recreates all tables.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite://")


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    if TEST_DATABASE_URL.startswith("sqlite"):
        test_engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(test_engine.sync_engine, "connect")
        def _enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    else:
        test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    async with test_engine.begin() as conn:
        if test_engine.dialect.name == "postgresql":
            # Reset the whole schema rather than drop_all(): drop_all only knows today's tables, so a
            # table left over from an older schema (still referencing trip/user) would block it.
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        else:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    yield test_engine

    await test_engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
