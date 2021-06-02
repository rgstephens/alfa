import datetime as dt
import logging
from functools import wraps
from typing import Any, Callable

import pytz

logger = logging.getLogger(__name__)


def get_now() -> dt.datetime:
    return dt.datetime.now(pytz.utc).replace(second=0, microsecond=0)


def get_now_with_seconds() -> dt.datetime:
    return dt.datetime.now(pytz.utc).replace(microsecond=0)


def run_once(f: Callable[..., Any]) -> Callable[..., Any]:
    running = False

    @wraps(f)
    async def wrapper() -> Any:
        nonlocal running
        if running:
            logger.debug(f'{f.__qualname__} already running')
            return

        logger.debug(f'{f.__qualname__} is not running, run it')
        running = True
        result: Any = None
        try:
            result = await f()
        finally:
            running = False
        return result

    return wrapper
