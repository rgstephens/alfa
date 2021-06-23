from __future__ import annotations

import inspect
import logging
from functools import wraps
from typing import Any, Callable, Dict, Optional, cast

from jaeger_client import Config, Tracer
from jaeger_client.span import Span
from opentracing.ext import tags
from opentracing.propagation import Format
from opentracing.scope_managers.contextvars import ContextVarsScopeManager

tracer: Tracer
logger = logging.getLogger(__name__)


class IsAwaitable(Exception):
    ...


class IsNotAwaitable(Exception):
    ...


def configure_tracing(app_name: str, host: str, port: int, propagation: str, jaeger_enabled: bool) -> Tracer:
    global tracer
    config = Config(
        config={
            'sampler': {'type': 'const', 'param': 1},
            'logging': False,
            'local_agent': {'reporting_host': host, 'reporting_port': port},
            'propagation': propagation,
            'enabled': jaeger_enabled,
        },
        validate=True,
        scope_manager=ContextVarsScopeManager(),
        service_name=app_name,
    )
    _tracer: Optional[Tracer] = config.initialize_tracer()
    if _tracer:
        tracer = _tracer
    return tracer


def get_tracer() -> Tracer:
    global tracer
    if not tracer:
        logger.warning('configure_tracing first')
    assert tracer
    return tracer


def get_current_span() -> Optional[Span]:
    tracer = get_tracer()
    active = tracer.scope_manager.active
    return cast(Span, active.span) if active else None


def get_current_trace_id() -> Optional[str]:
    span = get_current_span()
    trace_id = span.trace_id if span else None
    return '{:x}'.format(trace_id) if trace_id else None


def get_tracing_http_headers() -> Dict[str, str]:
    tracer = get_tracer()
    span = get_current_span()
    if not span:
        return {}
    span.set_tag(tags.SPAN_KIND, tags.SPAN_KIND_RPC_CLIENT)
    headers: Dict[str, str] = {}
    tracer.inject(span, Format.HTTP_HEADERS, headers)
    return headers


def _get_span_and_scope(f: Callable[..., Any], **kwargs: Any):
    db_query = kwargs.get('query', None)
    current_tags = {}
    if db_query is not None:
        current_tags[tags.DATABASE_TYPE] = 'postgres'
        current_tags[tags.DATABASE_STATEMENT] = db_query

    tracer = get_tracer()
    span = tracer.start_span(operation_name=f.__qualname__, child_of=get_current_span(), tags=current_tags)
    scope = tracer.scope_manager.activate(span, True)
    return span, scope


def trace_fn(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Используется для отслеживания синхронных функций.

    Пример
    ------
    >>> @trace_fn
    ... def any_function(*args, **kwargs):
    ...     pass
    ...
    """
    if inspect.iscoroutinefunction(f):
        raise IsAwaitable(f'{f.__qualname__} is awaitable. Use @trace_async_fn decorator instead.')

    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        span, scope = _get_span_and_scope(f, **kwargs)
        try:
            result = f(*args, **kwargs)
        except Exception as error:
            span.set_tag(tags.ERROR, True)
            span.set_tag('error.message', str(error))
            raise error
        finally:
            scope.close()
        return result

    return wrapper


def trace_async_fn(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Используется для отслеживания асинхронных функций.

    Пример
    ------
    >>> @trace_async_fn
    ... async def any_function(*args, **kwargs):
    ...     pass
    ...
    """
    if not inspect.iscoroutinefunction(f):
        raise IsNotAwaitable(f'{f.__qualname__} is not awaitable. Use @trace_fn decorator instead.')

    @wraps(f)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        span, scope = _get_span_and_scope(f, **kwargs)
        try:
            result = await f(*args, **kwargs)
        except Exception as error:
            span.set_tag(tags.ERROR, True)
            span.set_tag('error.message', str(error))
            raise error
        finally:
            scope.close()
        return result

    return wrapper


def trace_method(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Используется для отслеживания синхронных методов.

    Пример
    ------
    >>> class AnyClass:
    ...     @trace_method
    ...     def any_method(self, *args, **kwargs):
    ...         pass
    ...
    """
    if inspect.iscoroutinefunction(f):
        raise IsAwaitable(f'{f.__qualname__} is awaitable. Use @trace_async_method decorator instead.')

    @wraps(f)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        span, scope = _get_span_and_scope(f, **kwargs)
        try:
            result = f(self, *args, **kwargs)
        except Exception as error:
            span.set_tag(tags.ERROR, True)
            span.set_tag('error.message', str(error))
            raise error
        finally:
            scope.close()
        return result

    return wrapper


def trace_async_method(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Используется для отслеживания асинхронных методов.

    Пример
    ------
    >>> class AnyClass:
    ...     @trace_async_method
    ...     async def any_method(self, *args, **kwargs):
    ...         pass
    ...
    """
    if not inspect.iscoroutinefunction(f):
        raise IsNotAwaitable(f'{f.__qualname__} is not awaitable. Use @trace_method decorator instead.')

    @wraps(f)
    async def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        span, scope = _get_span_and_scope(f, **kwargs)
        try:
            result = await f(self, *args, **kwargs)
        except Exception as error:
            span.set_tag(tags.ERROR, True)
            span.set_tag('error.message', str(error))
            raise error
        finally:
            scope.close()
        return result

    return wrapper


def trace_classmethod(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Используется для отслеживания синхронных классовых методов.

    Пример
    ------
    >>> class AnyClass:
    ...     @classmethod
    ...     @trace_classmethod
    ...     def any_method(cls, *args, **kwargs):
    ...         pass
    ...
    """
    if inspect.iscoroutinefunction(f):
        raise IsAwaitable(f'{f.__qualname__} is awaitable. Use @trace_async_classmethod decorator instead.')

    @wraps(f)
    def wrapper(cls, *args: Any, **kwargs: Any) -> Any:
        span, scope = _get_span_and_scope(f, **kwargs)
        try:
            result = f(cls, *args, **kwargs)
        except Exception as error:
            span.set_tag(tags.ERROR, True)
            span.set_tag('error.message', str(error))
            raise error
        finally:
            scope.close()
        return result

    return wrapper


def trace_async_classmethod(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Используется для отслеживания асинхронных классовых методов.

    Пример
    ------
    >>> class AnyClass:
    ...     @classmethod
    ...     @trace_async_classmethod
    ...     async def any_method(cls, *args, **kwargs):
    ...         pass
    ...
    """
    if not inspect.iscoroutinefunction(f):
        raise IsNotAwaitable(f'{f.__qualname__} is not awaitable. Use @trace_classmethod decorator instead.')

    @wraps(f)
    async def wrapper(cls, *args: Any, **kwargs: Any) -> Any:
        span, scope = _get_span_and_scope(f, **kwargs)
        try:
            result = await f(cls, *args, **kwargs)
        except Exception as error:
            span.set_tag(tags.ERROR, True)
            span.set_tag('error.message', str(error))
            raise error
        finally:
            scope.close()
        return result

    return wrapper


new_span = trace_async_classmethod
new_async_span = trace_async_classmethod
new_sync_span = trace_classmethod
