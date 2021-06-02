import uvicorn

from .main import get_http_server


def test_get_http_server() -> uvicorn.Server:
    server = get_http_server()
    assert server
