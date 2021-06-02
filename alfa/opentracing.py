from __future__ import annotations

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


def new_span(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    async def wrapper(cls: Any, *args: Any, **kwargs: Any) -> Any:
        db_query = kwargs.get('query', None)
        current_tags = {}
        if db_query is not None:
            current_tags[tags.DATABASE_TYPE] = 'postgres'
            current_tags[tags.DATABASE_STATEMENT] = db_query

        tracer = get_tracer()
        span = tracer.start_span(operation_name=f.__qualname__, child_of=get_current_span(), tags=current_tags)
        scope = tracer.scope_manager.activate(span, True)
        try:
            result = await f(cls, *args, **kwargs)
        except Exception as exp:
            span.set_tag(tags.ERROR, True)
            span.set_tag('error.message', str(exp))
            raise exp
        finally:
            scope.close()
        return result

    return wrapper


def new_sync_span(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def wrapper(cls: Any, *args: Any, **kwargs: Any) -> Any:
        db_query = kwargs.get('query', None)
        current_tags = {}
        if db_query is not None:
            current_tags[tags.DATABASE_TYPE] = 'postgres'
            current_tags[tags.DATABASE_STATEMENT] = db_query

        tracer = get_tracer()
        span = tracer.start_span(operation_name=f.__qualname__, child_of=get_current_span(), tags=current_tags)
        scope = tracer.scope_manager.activate(span, True)
        try:
            result = f(cls, *args, **kwargs)
        except Exception as exp:
            span.set_tag(tags.ERROR, True)
            span.set_tag('error.message', str(exp))
            raise exp
        finally:
            scope.close()
        return result

    return wrapper


new_async_span = new_span
