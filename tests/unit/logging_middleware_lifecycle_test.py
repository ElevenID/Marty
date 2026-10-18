"""Exercise the retained ASGI middleware with real injected logging output."""

import json
import subprocess
import sys

import pytest


PROGRAM = """
import asyncio, logging, sys
from pathlib import Path
from types import SimpleNamespace
from marty_common.logging.structured_logging import LoggingMiddleware, setup_logging_for_service

mode = sys.argv[1]
config = setup_logging_for_service('application-owner', environment='production',
    enable_console=False, enable_file=False, log_dir='configured')
logger = config.get_logger()
handlers = list(logging.getLogger().handlers)
existing = set(Path.cwd().iterdir())
config.set_request_context(request_id='outer')
messages = []
ready = {}

async def receive():
    return {'type': 'http.request', 'body': b''}
async def send(message):
    messages.append(message)
async def app(scope, receive, send):
    if mode == 'concurrent':
        name = scope['path']
        other = '/b' if name == '/a' else '/a'
        ready[name].set()
        await ready[other].wait()
    logger.info('application-work', endpoint=scope['path'])
    if mode == 'error':
        raise ValueError('application failure')
    if mode == 'cancel':
        raise asyncio.CancelledError()
    if scope['type'] == 'websocket':
        await send({'type': 'websocket.accept'})
        return
    await send({'type': 'http.response.start', 'status': 201})
    await send({'type': 'http.response.body', 'body': b'ab', 'more_body': True})
    await send({'type': 'http.response.body', 'body': b'cde'})

middleware = LoggingMiddleware(app, logger)
if mode == 'logging-error':
    def fail(**kwargs):
        raise RuntimeError('logging failure')
    middleware.performance_logger = SimpleNamespace(log_request=fail)

def scope(path):
    return {'type': 'websocket' if mode == 'websocket' else 'http',
            'method': 'POST', 'path': path,
            'client': None if mode == 'no-client' else ('127.0.0.1', 1234)}

async def main():
    if mode == 'concurrent':
        ready.update({name: asyncio.Event() for name in ('/a', '/b')})
        await asyncio.gather(middleware(scope('/a'), receive, send),
                             middleware(scope('/b'), receive, send))
        return
    try:
        await middleware(scope('/a'), receive, send)
    except ValueError as error:
        assert mode == 'error' and str(error) == 'application failure'
    except asyncio.CancelledError:
        assert mode == 'cancel'
    except RuntimeError as error:
        assert mode == 'logging-error' and str(error) == 'logging failure'
    else:
        assert mode not in ('error', 'cancel', 'logging-error')

asyncio.run(main())
logger.info('after-request')
assert list(logging.getLogger().handlers) == handlers
assert set(Path.cwd().iterdir()) == existing
if mode in ('success', 'no-client', 'logging-error'):
    assert [m['type'] for m in messages] == [
        'http.response.start', 'http.response.body', 'http.response.body']
elif mode == 'websocket':
    assert messages == [{'type': 'websocket.accept'}]
logging.shutdown()
"""


@pytest.mark.parametrize('mode', ['success', 'no-client', 'error', 'cancel', 'logging-error',
                                  'websocket', 'concurrent'])
def test_middleware_uses_injected_logger_and_restores_context(mode, tmp_path):
    result = subprocess.run([sys.executable, '-c', PROGRAM, mode], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert all(event['service'] == 'application-owner' for event in events)
    assert events[-1]['event'] == 'after-request'
    assert events[-1]['request_id'] == 'outer'
    requests = [event for event in events if event['event'] == 'http_request']
    if mode in ('websocket', 'logging-error'):
        assert not requests
    else:
        assert len(requests) == (2 if mode == 'concurrent' else 1)
        for event in requests:
            assert event['status_code'] == (500 if mode in ('error', 'cancel') else 201)
            assert event['response_size'] == (0 if mode in ('error', 'cancel') else 5)
            assert event['client_ip'] == ('unknown' if mode == 'no-client' else '127.0.0.1')
            assert event['request_id'] != 'outer'
        if mode == 'concurrent':
            assert len({event['request_id'] for event in requests}) == 2
            work = {event['endpoint']: event['request_id'] for event in events
                    if event['event'] == 'application-work'}
            assert work == {event['endpoint']: event['request_id'] for event in requests}
    errors = [event for event in events if event['event'] == 'request_error']
    assert len(errors) == (1 if mode == 'error' else 0)
    if errors:
        assert errors[0]['error_type'] == 'ValueError'
        assert errors[0]['request_id'] == requests[0]['request_id']
