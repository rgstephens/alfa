import logging
import os

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, generate_latest, multiprocess
from starlette.responses import Response

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get('/alive', response_class=PlainTextResponse)
async def alive() -> PlainTextResponse:
    return PlainTextResponse('OK')


@router.get('/metrics')
async def metrics() -> Response:
    registry = REGISTRY
    if 'prometheus_multiproc_dir' in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)

    headers = {'Content-Type': CONTENT_TYPE_LATEST}
    return Response(generate_latest(registry), status_code=200, headers=headers)


@router.get('/error')
async def error() -> None:
    logger.error('test exception via logging')
    raise Exception('test exception via raise')
