import logging
from functools import wraps
from logging import LogRecord, config
from typing import Any, Callable, Dict

import coloredlogs


class ExtraFormatter(coloredlogs.ColoredFormatter):
    """
    небольшой хак, чтобы поддерать %(props)s в формате логов и для json и для обычного форматтера
    """

    def formatMessage(self, record: LogRecord) -> Any:
        if not hasattr(record, 'props'):
            record.props = ''  # type: ignore[attr-defined]
        return super().formatMessage(record)


def _get_configure_logging() -> Dict[str, Any]:
    _format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s %(props)s'
    formatter = 'alfa.logger.ExtraFormatter'
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {'default': {'format': _format, 'class': formatter}},
        'handlers': {'default': {'class': 'logging.StreamHandler', 'formatter': 'default'}},
        'root': {'handlers': ['default'], 'level': logging.INFO},
        'loggers': {'': {'handlers': ['default'], 'level': logging.INFO, 'propagate': False}},
    }


def configure_logging() -> None:
    config.dictConfig(_get_configure_logging())


def log_extra(**kwargs: Any) -> Dict[str, Any]:
    return {'extra': {'props': {'data': kwargs}}}


def log_method(logger_name: str) -> Callable[..., Any]:
    def wrapper(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        async def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:

            _logger = logging.getLogger(logger_name)
            if args:
                _logger.debug(f'{f.__qualname__}: start', **log_extra(args=args))
            else:
                _logger.debug(f'{f.__qualname__}: start')
            result: Any = await f(self, *args, **kwargs)
            _logger.debug(f'{f.__qualname__}: finish')

            return result

        return wrapped

    return wrapper


def log_sync_method(logger_name: str) -> Callable[..., Any]:
    def wrapper(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:

            _logger = logging.getLogger(logger_name)
            if args:
                _logger.debug(f'{f.__qualname__}: start', **log_extra(args=args))
            else:
                _logger.debug(f'{f.__qualname__}: start')
            result: Any = f(self, *args, **kwargs)
            _logger.debug(f'{f.__qualname__}: finish')

            return result

        return wrapped

    return wrapper
