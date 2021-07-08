import logging
from datetime import datetime, timezone
from functools import wraps
from logging import LogRecord, config
from typing import Any, Callable, Dict, Optional

import coloredlogs
from pythonjsonlogger.jsonlogger import JsonFormatter, merge_record_extra


class ExtraFormatter(coloredlogs.ColoredFormatter):
    """
    небольшой хак, чтобы поддерать %(props)s в формате логов и для json и для обычного форматтера
    """

    def formatMessage(self, record: LogRecord) -> Any:
        if not hasattr(record, 'props'):
            record.props = ''  # type: ignore[attr-defined]
        return super().formatMessage(record)


class MyJsonFormatter(JsonFormatter):
    RENAME_FIELDS = {'levelname': 'level', 'asctime': 'ts', 'message': 'msg', 'name': 'caller'}

    def add_fields(self, log_record, record, message_dict):
        """
        Override this method to implement custom logic for adding fields.
        """
        for field in self._required_fields:
            if field in self.RENAME_FIELDS:
                log_record[self.RENAME_FIELDS[field]] = record.__dict__.get(field)
            else:
                log_record[field] = record.__dict__.get(field)
        log_record.update(message_dict)
        merge_record_extra(record, log_record, reserved=self._skip_fields)

        if self.timestamp:
            key = self.timestamp if type(self.timestamp) == str else 'timestamp'
            log_record[key] = datetime.fromtimestamp(record.created, tz=timezone.utc)


def _get_logger_level(logger_name: str, debug_loggers: Optional[list[str]] = None) -> int:
    if debug_loggers is None:
        debug_loggers = []

    if 'all' in debug_loggers:
        return logging.DEBUG
    else:
        return logging.DEBUG if logger_name in debug_loggers else logging.INFO


def configure_logging(
    loggers: Optional[list[str]] = None, enable_json: bool = False, debug_loggers: Optional[list[str]] = None
) -> Dict[str, Any]:
    if enable_json:
        _format = '%(asctime)s %(levelname)s [%(name)s] %(message)s %(props)s'
        formatter = 'alfa.logger.MyJsonFormatter'
    else:
        _format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s %(props)s'
        formatter = 'alfa.logger.ExtraFormatter'

    _loggers = {
        _name: {'handlers': ['default'], 'level': _get_logger_level(_name, debug_loggers), 'propagate': False}
        for _name in (loggers or [])
    }
    _config: dict[str, Any] = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {'default': {'format': _format, 'class': formatter}},
        'handlers': {'default': {'class': 'logging.StreamHandler', 'formatter': 'default'}},
        'root': {'handlers': ['default'], 'level': logging.INFO},
        'loggers': {'': {'handlers': ['default'], 'level': logging.INFO, 'propagate': False}, **_loggers},
    }
    config.dictConfig(_config)
    return _config


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
