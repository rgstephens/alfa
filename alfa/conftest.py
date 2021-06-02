# conftest.py
import sys
from os.path import abspath, dirname

import pytest

root_dir = dirname(abspath(__file__))
sys.path.append(root_dir)


@pytest.fixture(scope='session', autouse=True)
def test_configure_tracing() -> None:
    from alfa.opentracing import configure_tracing

    configure_tracing('test', '127.0.0.1', 1111, 'b3', False)
