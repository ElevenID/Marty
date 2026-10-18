"""Retained logging startup must emit real structured events."""

import json
import subprocess
import sys


def test_structured_logging_starts_and_merges_request_and_contextvars(tmp_path):
    # Isolate process-wide structlog/root logging configuration from other tests.
    result = subprocess.run(
        [sys.executable, "-c", """
from marty_common.logging.structured_logging import setup_logging_for_service
from structlog.contextvars import bound_contextvars
config = setup_logging_for_service('compatibility-worker', environment='production',
                                   enable_console=False, enable_file=False)
with bound_contextvars(operation_id='operation-1'):
    with config.request_context(request_id='request-1'):
        config.get_logger().info('request-completed', success=True)
config.get_logger().info('outside-request')
"""],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    first, second = [json.loads(line) for line in result.stdout.splitlines()]
    assert first['service'] == 'compatibility-worker'
    assert first['request_id'] == 'request-1'
    assert first['operation_id'] == 'operation-1'
    assert first['event'] == 'request-completed'
    assert first['success'] is True
    assert second['event'] == 'outside-request'
    assert 'request_id' not in second
    assert 'operation_id' not in second


def test_standard_logging_file_contains_service_and_request_context(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", """
import logging
from marty_common.logging.structured_logging import setup_logging_for_service
config = setup_logging_for_service('compatibility-worker', version='test-version',
    environment='production', enable_console=False, enable_file=True)
with config.request_context(request_id='request-1'):
    logging.getLogger('standard').info('standard-event')
logging.shutdown()
"""],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    event = json.loads((tmp_path / 'logs/compatibility-worker.log').read_text())
    assert event['message'] == 'standard-event'
    assert event['service'] == 'compatibility-worker'
    assert event['version'] == 'test-version'
    assert event['environment'] == 'production'
    assert event['request_id'] == 'request-1'
