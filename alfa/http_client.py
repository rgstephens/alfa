import logging
from logging import Logger
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx
import orjson

from .logger import log_extra
from .opentracing import get_tracing_http_headers

CONTENT_TYPE = 'application/json'


class HttpClientMixin:
    host: str
    logger_name: str
    logger: Logger
    timeout: float
    app_name: str
    app_version: str
    content_type: str = 'application/json'

    def __init__(self, host: str, port: int, timeout: float, logger_name: str, app_name: str, app_version: str) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.logger_name = logger_name
        self.logger = logging.getLogger(self.logger_name)
        self.app_name = app_name
        self.app_version = app_version

    def _get_url(self, url: str) -> str:
        return urljoin(self.host, url)

    def _get_json_body(self, data: Dict[Any, Any]) -> str:
        return orjson.dumps(data).decode()

    def _get_default_headers(self) -> Dict[str, str]:
        return {
            'content-type': self.content_type,
            'X-APP-NAME': self.app_name,
            'X-APP-VERSION': self.app_version,
        }

    def _build_headers(self, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        default_headers = self._get_default_headers()
        if not headers:
            headers = default_headers
        else:
            headers.update(default_headers)
        headers.update(get_tracing_http_headers())
        return headers

    async def _get_parsed_response(self, url: str, body: str, headers: Optional[Dict[str, str]] = None) -> Any:
        headers = self._build_headers(headers=headers)
        self.logger.debug('request', **log_extra(url=url, body=body, headers=headers))
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(url, data=body, timeout=self.timeout, headers=headers or {})  # type: ignore [arg-type]
        except Exception:
            self.logger.exception(f'{self.logger_name}: unknown http error')
            return
        else:
            self.logger.debug('response', **log_extra(url=url, response=r.content))

        try:
            data = r.json()
        except Exception:
            self.logger.exception(f'{self.logger_name}: cant parse json', **log_extra(content=r.content))
            return
        else:
            return data if r.status_code == 200 else None
