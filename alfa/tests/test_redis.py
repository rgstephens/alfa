from alfa import redis
import pytest


@pytest.mark.asyncio
async def test_redis() -> None:
    redis.init_config(
        host='0.0.0.0',
        port=6379,
        minsize=5,
        maxsize=10
    )

    ok, error = await redis.check_conn()
    assert ok
    assert error == ''
