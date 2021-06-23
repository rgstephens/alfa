import asyncio
import datetime as dt
import logging

import uvicorn
from fastapi import APIRouter, FastAPI

from alfa.dto import StrictBaseDTO
from alfa.handler import router as maintenance_router
from alfa.logger import _get_configure_logging, log_method, log_sync_method
from alfa.middleware import (
    AccessLogMiddleware,
    ExceptionMiddleware,
    PrometheusMiddleware,
    StarletteTracingMiddleWare,
    TracingResponseHeadersMiddleware,
)
from alfa.opentracing import (
    configure_tracing,
    get_current_span,
    get_current_trace_id,
    get_tracer,
    get_tracing_http_headers,
    trace_async_classmethod,
    trace_async_fn,
    trace_async_method,
    trace_classmethod,
    trace_fn,
    trace_method,
)
from alfa.sentry import configure_sentry
from alfa.server import MyORJSONResponse, install_http_server
from alfa.utils import get_now

logger = logging.getLogger(__name__)
router = APIRouter()


class TestResp(StrictBaseDTO):
    x: int
    now: dt.datetime


class TestService:
    @classmethod
    @trace_async_classmethod
    @log_method('test')
    async def test_async_classmethod(cls) -> None:
        pass

    @classmethod
    @trace_classmethod
    @log_sync_method('test')
    def test_sync_classmethod(cls) -> None:
        pass

    @trace_async_method
    async def test_async_method(self) -> None:
        pass

    @trace_method
    def test_sync_method(self) -> None:
        pass


@trace_fn
def test_sync_fn() -> None:
    pass


@trace_async_fn
async def test_async_fn() -> None:
    pass


@router.get('/test', response_model=TestResp)
async def version() -> MyORJSONResponse:
    tracer = get_tracer()

    with tracer.start_active_span('foo', finish_on_close=True):
        with tracer.start_active_span('bar', finish_on_close=True):

            await TestService.test_async_classmethod()
            TestService.test_sync_classmethod()

            await TestService().test_async_method()
            TestService().test_sync_method()

            await test_async_fn()
            test_sync_fn()

            with tracer.start_active_span('baz', finish_on_close=True):
                logger.info(f'{tracer=}')
                logger.info(f'trace_id: {get_current_trace_id()}')
                logger.info(f'span: {get_current_span()}')
                logger.info(f'tracing_http_headers: {get_tracing_http_headers()}')
                logger.info("Hello world from OpenTelemetry Python!")

    return MyORJSONResponse(content=TestResp(x=1, now=get_now()))


def get_http_server() -> uvicorn.Server:
    configure_tracing('alfa', '127.0.0.1', 6831, 'b3', True)
    configure_sentry('', '', '', True)

    uvicorn_server: uvicorn.Server = install_http_server(
        'test', '/openapi.json', '0.0.0.0', 8000, _get_configure_logging()
    )
    app: FastAPI = uvicorn_server.config.app

    # add middlewares
    app.add_middleware(
        PrometheusMiddleware,
        group_paths=True,
        service_name='alfa',
        service_namespace='mdcm',
        service_version='0.0.1',
        service_instance_id='unknown',
    )
    app.add_middleware(ExceptionMiddleware)
    app.add_middleware(TracingResponseHeadersMiddleware)
    app.add_middleware(AccessLogMiddleware)
    tracer = get_tracer()
    if tracer:
        app.add_middleware(StarletteTracingMiddleWare, tracer=tracer, component_name='alfa')

    # add routing
    app.include_router(router, tags=['Test'])
    app.include_router(maintenance_router, tags=['Maintenance'])

    return uvicorn_server


if __name__ == "__main__":
    uvicorn_server = get_http_server()
    asyncio.run(uvicorn_server.serve())
