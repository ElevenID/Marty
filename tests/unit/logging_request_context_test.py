"""Real logging output must preserve request context across concurrent work."""

import json
import subprocess
import sys

import pytest


PROGRAM = """
import asyncio, logging, sys, threading
from concurrent.futures import ThreadPoolExecutor
from marty_common.logging.structured_logging import setup_logging_for_service

config = setup_logging_for_service('context-test', environment='production',
                                   enable_console=False, enable_file=True)
logger = config.get_logger()
def emit(label):
    logger.info(label)
    logging.getLogger('standard').info(label)

mode = sys.argv[1]
if mode == 'async':
    async def main():
        ready = {name: asyncio.Event() for name in ('a', 'b')}
        emitted = {name: asyncio.Event() for name in ('a', 'b')}
        async def request(name, other):
            with config.request_context(request_id=name, ignored='not emitted'):
                ready[name].set()
                await ready[other].wait()
                emit(name)
                emitted[name].set()
                await emitted[other].wait()
        await asyncio.gather(request('a', 'b'), request('b', 'a'))
    asyncio.run(main())
elif mode == 'thread':
    barrier = threading.Barrier(2, timeout=5)
    def request(name):
        with config.request_context(request_id=name, ignored='not emitted'):
            barrier.wait()
            emit(name)
            barrier.wait()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(request, ('a', 'b')))
else:
    config.set_request_context(request_id='root')
    with config.request_context(request_id='outer'):
        emit('outer')
        try:
            with config.request_context(request_id='inner'):
                emit('inner')
                config.clear_request_context()
                emit('cleared-inner')
                raise ValueError('exercise exceptional exit')
        except ValueError:
            pass
        emit('restored-outer')
    emit('restored-root')
    config.clear_request_context()
emit('outside')
logging.shutdown()
"""


@pytest.mark.parametrize('mode', ['async', 'thread', 'nested'])
def test_request_context_is_isolated_and_restored_in_both_outputs(mode, tmp_path):
    result = subprocess.run(
        [sys.executable, '-c', PROGRAM, mode], cwd=tmp_path,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    structured = [json.loads(line) for line in result.stdout.splitlines()]
    standard = [json.loads(line) for line in
                (tmp_path / 'logs/context-test.log').read_text().splitlines()]
    expected = ({'a': 'a', 'b': 'b', 'outside': None} if mode != 'nested' else {
        'outer': 'outer', 'inner': 'inner', 'cleared-inner': None,
        'restored-outer': 'outer', 'restored-root': 'root', 'outside': None,
    })
    for events, label_key in [(structured, 'event'), (standard, 'message')]:
        assert len(events) == len(expected)
        assert {event[label_key]: event.get('request_id') for event in events} == expected
        for event in events:
            assert 'ignored' not in event
            if expected[event[label_key]] is not None:
                assert event['user_id'] is None
                assert event['session_id'] is None
                assert event['correlation_id'] is None
            else:
                assert 'request_id' not in event
