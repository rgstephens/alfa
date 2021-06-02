import datetime as dt
from decimal import Decimal
from typing import Any, Dict, Optional, Union

import orjson
import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import JSONResponse  # noqa

from alfa.opentracing import new_sync_span

from .dto import BaseDTO, InvalidRequestError


def default(obj: Any) -> Any:
    if isinstance(obj, BaseDTO):
        return obj.dict()
    if isinstance(obj, Decimal):
        return float(str(obj))
    if isinstance(obj, dt.date):
        return obj.isoformat()
    if isinstance(obj, dt.datetime):
        if not obj.tzinfo:
            return obj.strftime('%Y-%m-%dT%H:%M:%S.%f+00:00')
        else:
            return obj.isoformat()
    if isinstance(obj, dt.time):
        return obj.strftime('%H:%M')
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    raise TypeError


def serialize_to_bytes(content: Any) -> bytes:
    if isinstance(content, bytes):
        return content
    return orjson.dumps(content, option=orjson.OPT_PASSTHROUGH_DATETIME, default=default)


class MyORJSONResponse(JSONResponse):
    media_type = 'application/json'

    @new_sync_span
    def render(self, content: Any) -> bytes:
        return serialize_to_bytes(content)


def get_error(error_responses: Dict[Union[int, str], Dict[str, Any]], status: int, error_code: str) -> MyORJSONResponse:
    return MyORJSONResponse(status_code=status, content=error_responses[status]['model'](code=error_code).dict())


def use_route_names_as_operation_ids(app: FastAPI) -> None:
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.path.replace('/', '_')[1:]


def install_http_server(
    title: str,
    openapi_url: str,
    http_host: str,
    http_port: int,
    configure_logging: Dict[str, Any],
    limit_concurrency: Optional[int] = None,
    timeout_keep_alive: int = 5,
) -> uvicorn.Server:
    # init fastapi app
    app = FastAPI(title=title, openapi_url=openapi_url, default_response_class=ORJSONResponse)

    # set host/port
    config = uvicorn.Config(
        app,
        host=http_host,
        port=http_port,
        log_config=configure_logging,
        access_log=False,
        limit_concurrency=limit_concurrency,
        timeout_keep_alive=timeout_keep_alive,
    )
    uvicorn_server = uvicorn.Server(config=config)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=400,
            content=InvalidRequestError(
                code=InvalidRequestError.ErrorCode.INVALID_REQUEST, details=exc.errors()
            ).dict(),
        )

    use_route_names_as_operation_ids(app)

    # skip uvicorn signals handling
    do_nothing = lambda *args: None
    uvicorn_server.install_signal_handlers = do_nothing
    return uvicorn_server
