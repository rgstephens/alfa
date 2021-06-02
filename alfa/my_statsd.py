import logging
from typing import Optional

from statsd import StatsClient

logger = logging.getLogger(__name__)
statsd_client: StatsClient


def configure_statsd(host: str, port: int, prefix: Optional[str] = None) -> StatsClient:
    global statsd_client
    statsd_client = StatsClient(host=host, port=port, prefix=prefix)
    return statsd_client


def get_statsd_client() -> StatsClient:
    global statsd_client
    if not statsd_client:
        logger.warning('configure_statsd first')
    assert statsd_client
    return statsd_client
