import uvicorn

from alfa.commands import get_db_docs, get_openapi_docs
from alfa.logger import configure_logging
from alfa.server import install_http_server


def test_commands() -> None:
    get_db_docs([])

    uvicorn_server: uvicorn.Server = install_http_server('test', '/openapi.json', '0.0.0.0', 8000, configure_logging())
    get_openapi_docs(uvicorn_server)
