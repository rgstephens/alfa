import logging
from dataclasses import dataclass
from typing import Optional
from typing import Tuple

import aioredis
from aioredlock import Aioredlock


logger = logging.getLogger(__name__)


@dataclass
class Config:
    host: str
    port: int
    minsize: int
    maxsize: int
    locks_db: int


_CONFIG: Optional[Config] = None
_REDIS_CONN: Optional[aioredis.Redis] = None
_REDIS_LOCK_MANGER: Optional[Aioredlock] = None


def init_config(
    host: str,
    port: int,
    minsize: int,
    maxsize: int,
    locks_db: int = 1,
) -> None:
    global _CONFIG

    _CONFIG = Config(
        host=host,
        port=port,
        minsize=minsize,
        maxsize=maxsize,
        locks_db=locks_db,
    )


async def _init() -> Tuple[aioredis.Redis, Aioredlock]:
    if not _CONFIG:
        raise Exception('Redis not configured. Run init_config(...).')

    global _REDIS_CONN
    global _REDIS_LOCK_MANGER

    if not _REDIS_CONN:
        _REDIS_CONN = await aioredis.create_redis_pool(
            f'redis://{_CONFIG.host}:{_CONFIG.port}',
            minsize=_CONFIG.minsize,
            maxsize=_CONFIG.maxsize,
        )

    if not _REDIS_LOCK_MANGER:
        _REDIS_LOCK_MANGER = Aioredlock([{
            'host': _CONFIG.host,
            'port': _CONFIG.port,
            'db': _CONFIG.locks_db,
        }])

    return _REDIS_CONN, _REDIS_LOCK_MANGER


async def get_conn() -> aioredis.Redis:
    global _REDIS_CONN

    if not _REDIS_CONN:
        _REDIS_CONN, _ = await _init()

    return _REDIS_CONN


async def get_lock_manager() -> Aioredlock:
    global _REDIS_LOCK_MANGER

    if not _REDIS_LOCK_MANGER:
        _, _REDIS_LOCK_MANGER = await _init()

    return _REDIS_LOCK_MANGER


async def close() -> None:
    global _REDIS_CONN
    global _REDIS_LOCK_MANGER

    if _REDIS_CONN:
        _REDIS_CONN.close()
        await _REDIS_CONN.wait_closed()

    if _REDIS_LOCK_MANGER:
        try:
            await _REDIS_LOCK_MANGER.destroy()
        except Exception:
            logger.info('cant close redis connection for distributed lock')
        else:
            logger.info('close redis connection for distributed lock')


async def check_conn() -> Tuple[bool, str]:
    try:
        redis_conn = await get_conn()
        await redis_conn.set('test', '123')
        await redis_conn.get('test')
    except Exception as exp:
        logger.exception('unknown connection error')
        return False, str(exp)
    else:
        return True, ''
