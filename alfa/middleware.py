from __future__ import annotations

import logging
import time
from urllib.parse import urlunparse

import opentracing
from fastapi.responses import ORJSONResponse
from jaeger_client import Tracer
from opentracing.ext import tags
from prometheus_client import Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from alfa.logger import log_extra

from .dto import UnknownError
from .opentracing import get_current_trace_id, get_tracing_http_headers

logger = logging.getLogger(__name__)


class ExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception('unknown exception')
            return ORJSONResponse(status_code=500, content=UnknownError(code=UnknownError.ErrorCode.UNKNOWN).dict())
        else:
            return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        get_current_trace_id()
        start = time.monotonic()
        logger.info(f"request start", **log_extra(method=request.scope['method'], request_uri=request.scope['path'],))
        response = await call_next(request)
        duration = int((time.monotonic() - start) * 1000)
        logger.info(
            f"request end",
            **log_extra(
                method=request.scope['method'],
                status_code=response.status_code,
                request_uri=request.scope['path'],
                duration=duration,
            ),
        )
        return response


class TracingResponseHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = get_tracing_http_headers()
        trace_id = get_current_trace_id() or ''
        response.headers['x-trace-id'] = trace_id
        for _header in headers:
            response.headers[_header] = headers[_header]
        return response


labels = (
    'http_flavor',
    'http_host',
    'http_method',
    'http_route',
    'http_scheme',
    'http_server_name',
    'http_target',
    'http_status_code',
    'service_name',
    'service_namespace',
    'service_version',
    'service_instance_id',
)

REQUEST_TIME = Histogram(
    'http_server_duration',
    'http_server_duration server latency in seconds',
    labels,
    buckets=(
        0.0005,
        0.001,
        0.005,
        0.01,
        0.02,
        0.05,
        0.1,
        0.2,
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        1,
        1.5,
        2,
        2.5,
        3,
        3.5,
        4,
        4.5,
        5,
        5.5,
        6,
        6.5,
        7,
        7.5,
        8,
        8.5,
        9,
        9.5,
        10,
        11,
        12,
        13,
        14,
        15,
    ),
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Middleware that collects Prometheus metrics for each request.
    Use in conjuction with the Prometheus exporter endpoint handler.
    """

    def __init__(
        self,
        app: ASGIApp,
        group_paths: bool = False,
        service_name: str = 'unknown',
        service_namespace: str = 'unknown',
        service_version: str = 'unknown',
        service_instance_id: str = 'unknown',
    ):
        super().__init__(app)
        self.group_paths = group_paths
        self.service_name = service_name
        self.service_namespace = service_namespace
        self.service_version = service_version
        self.service_instance_id = service_instance_id

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        path = request.url.path
        begin = time.time()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            raise e
        finally:
            # group_paths enables returning the original router path (with url param names)
            # for example, when using this option, requests to /api/product/1 and /api/product/3
            # will both be grouped under /api/product/{product_id}. See the README for more info.
            if self.group_paths and request.scope.get('endpoint', None) and request.scope.get('router', None):
                try:
                    # try to match the request scope's handler function against one of handlers in the app's router.
                    # if a match is found, return the path used to mount the handler (e.g. api/product/{product_id}).
                    path = [
                        route
                        for route in request.scope['router'].routes
                        if (hasattr(route, 'endpoint') and route.endpoint == request.scope['endpoint'])
                        # for endpoints handled by another app, like fastapi.staticfiles.StaticFiles,
                        # check if the request endpoint matches a mounted app.
                        or (hasattr(route, 'app') and route.app == request.scope['endpoint'])
                    ][0].path
                except IndexError:
                    # no route matched.
                    # this can happen for routes that don't have an endpoint function.
                    pass
                except Exception as e:
                    logger.error(e)
            end = time.time()

            labels = [
                request.scope.get('http_version', 'unknown'),  # http_flavor
                request.headers.get('host', 'unknown'),  # http_host
                method,  # http_method
                path,  # http_route
                request.scope.get('scheme', 'unknown'),  # http_scheme
                'rpc',  # http_server_name
                path,  # http_target
                status_code,  # http_status_code
                self.service_name,  # service_name
                self.service_namespace,  # service_namespace
                self.service_version,  # service_version
                self.service_instance_id,  # service_instance_id
            ]
            # latency = (end - begin) * 1000  # in milliseconds
            latency = end - begin  # in seconds
            REQUEST_TIME.labels(*labels).observe(latency)

        return response


class StarletteTracingMiddleWare:
    def __init__(self, app: ASGIApp, tracer: Tracer, component_name: str):
        self._tracer = tracer
        self.component_name = component_name
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Skipping NON http and ASGI lifespan events
        if scope["type"] not in ["http", "websocket"]:
            return

        # Try to find and existing context in the provided request headers
        span_ctx = None
        headers = {}
        for k, v in scope["headers"]:
            headers[k.lower().decode("utf-8")] = v.decode("utf-8")
        try:
            span_ctx = self._tracer.extract(opentracing.Format.HTTP_HEADERS, headers)
        except (opentracing.propagation.InvalidCarrierException, opentracing.propagation.SpanContextCorruptedException):
            pass

        with self._tracer.start_active_span(
            str(scope["path"]), child_of=span_ctx, finish_on_close=True
        ) as tracing_scope:
            span = tracing_scope.span
            span.set_tag(tags.COMPONENT, self.component_name)
            span.set_tag(tags.SPAN_KIND, tags.SPAN_KIND_RPC_SERVER)
            span.set_tag(tags.HTTP_METHOD, scope["method"])
            host, port = scope["server"]
            url = urlunparse(
                (str(scope["scheme"]), f"{host}:{port}", str(scope["path"]), "", str(scope["query_string"]), "",)
            )
            span.set_tag(tags.HTTP_URL, url)
            await self.app(scope, receive, send)
            return
