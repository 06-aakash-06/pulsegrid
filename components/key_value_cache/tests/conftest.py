import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager

import pytest


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@contextmanager
def redis_server():
    port = free_port()
    with tempfile.TemporaryDirectory(prefix='pg-cache-redis-') as directory:
        process = subprocess.Popen(['redis-server', '--bind', '127.0.0.1', '--port', str(port),
                                    '--dir', directory, '--save', '', '--appendonly', 'no'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.05):
                        break
                except OSError:
                    time.sleep(.02)
            else:
                raise RuntimeError('Redis startup failed')
            yield port, process
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)


@pytest.fixture
def redis_node():
    with redis_server() as result:
        yield result
