import logging
from typing import Any, Dict, Optional

import sentry_sdk
from sentry_sdk import HttpTransport
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

logger = logging.getLogger(__name__)


class Transport(HttpTransport):
    def __init__(self, options: Dict[str, Any]) -> None:
        super().__init__(options)

    def _get_pool_options(self, ca_certs: Optional[Any]) -> Dict[str, Any]:
        return {"num_pools": 2, "cert_reqs": 'CERT_NONE', "retries": False}


def configure_sentry(dsn: str, environment_name: str, version: str, enabled: bool) -> None:
    if enabled and dsn:
        logger.info(f'Configure Sentry by {dsn}')
        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR,  # Capture info and above as breadcrumbs  # Send errors as events
        )
        sentry_sdk.init(
            environment=environment_name,
            release=version,
            dsn=dsn,
            transport=Transport,
            integrations=[AioHttpIntegration(), sentry_logging],
        )
