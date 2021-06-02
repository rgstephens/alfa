import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Tuple

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

__db_pool: Optional[AsyncEngine] = None
__sessionmaker: Optional[sessionmaker] = None


class PoolAlreadyInitialized(Exception):
    pass


class PoolNotInitialized(Exception):
    pass


def get_connection_url(host: str, port: int, username: str, password: str, database: str) -> URL:
    return URL('postgresql+asyncpg', host=host, port=port, username=username, password=password, database=database)


def init_db(connection_url: URL, echo: bool, pool_recycle_seconds: int, pool_size: int) -> AsyncEngine:
    global __db_pool
    global __sessionmaker
    if __db_pool is not None:
        raise PoolAlreadyInitialized('database already initialized')

    __db_pool = create_async_engine(
        connection_url, echo=echo, pool_recycle=pool_recycle_seconds, pool_size=pool_size, pool_pre_ping=True
    )
    __sessionmaker = sessionmaker(__db_pool, expire_on_commit=False, class_=AsyncSession)
    logger.info('database pool opened')
    assert __db_pool
    assert __sessionmaker
    return __db_pool


async def close_db() -> None:
    global __db_pool
    global __sessionmaker
    if __sessionmaker is not None:
        __sessionmaker.close_all()  # type: ignore
        __sessionmaker = None
    if __db_pool is not None:
        await __db_pool.dispose()
        __db_pool = None
    logger.info('database pool closed')


@asynccontextmanager
async def session_context_with_transaction() -> AsyncGenerator[AsyncSession, None]:
    if __sessionmaker is None:
        raise PoolNotInitialized()
    async with __sessionmaker() as session:
        async with session.begin():
            yield session


@asynccontextmanager
async def session_context() -> AsyncGenerator[AsyncSession, None]:
    if __sessionmaker is None:
        raise PoolNotInitialized()
    async with __sessionmaker() as session:
        yield session


@asynccontextmanager
async def connection_context() -> AsyncGenerator[AsyncSession, None]:
    if __db_pool is None:
        raise PoolNotInitialized()
    async with __db_pool.connect() as connection:
        yield connection


@asynccontextmanager
async def connection_context_with_transaction() -> AsyncGenerator[AsyncSession, None]:
    if __db_pool is None:
        raise PoolNotInitialized()
    async with __db_pool.connect() as connection:
        async with connection.begin():
            yield connection


async def get_db_pool() -> AsyncEngine:
    global __db_pool
    if not __db_pool:
        raise PoolNotInitialized('database not initialized')
    return __db_pool


async def check_db_connection() -> Tuple[bool, str]:
    global __db_pool
    global __sessionmaker
    if __db_pool is None:
        return False, '__db_pool is None'
    if __sessionmaker is None:
        return False, '__session_maker is None'
    try:
        async with __sessionmaker() as session:
            await session.execute('select 1;')
    except Exception as exp:
        logger.exception('unknown connection error')
        return False, str(exp)
    else:
        return True, ''


ModelBase = declarative_base()