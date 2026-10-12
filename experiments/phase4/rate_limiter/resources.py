"""Owned disposable Redis; no shared endpoints, flushes or credential generation."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
import redis

class DisposableRedis:
    def __init__(self):
        self.directory = tempfile.TemporaryDirectory(prefix='pg-phase41-')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.url = f'redis://127.0.0.1:{self.port}/0'
        self.process = None
        self.log = None
        self.image = os.environ.get("RATE_LIMITER_REDIS_IMAGE")
        self.container = None

    def start(self):
        if self.image:
            return self._start_container()
        executable = os.environ.get('RATE_LIMITER_REDIS_SERVER', 'redis-server')
        if not shutil.which(executable):
            raise RuntimeError('redis-server required; use RATE_LIMITER_REDIS_SERVER for Redis 7')
        self.log = open(Path(self.directory.name)/'redis.log', 'ab')
        self.process = subprocess.Popen([executable, '--bind', '127.0.0.1', '--port', str(self.port),
            '--save', '', '--appendonly', 'no', '--maxmemory', '64mb', '--maxmemory-policy', 'noeviction',
            '--dir', self.directory.name], stdout=self.log, stderr=self.log)
        client = redis.Redis.from_url(self.url, socket_timeout=.1)
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('Disposable Redis failed to start')
            try:
                if client.ping():
                    self.version = client.info('server')['redis_version']
                    client.close()
                    return self
            except redis.RedisError:
                time.sleep(.01)
        raise RuntimeError('Disposable Redis startup timeout')

    def _start_container(self):
        if self.container is None:
            self.container = 'pg-phase41-' + uuid.uuid4().hex[:12]
            subprocess.run(['docker', 'run', '-d', '--name', self.container,
                '--memory', '128m', '--cpus', '1', '-p', f'127.0.0.1:{self.port}:6379', self.image,
                'redis-server', '--save', '', '--appendonly', 'no', '--maxmemory', '64mb',
                '--maxmemory-policy', 'noeviction'], check=True, capture_output=True)
            published = subprocess.check_output(['docker','port',self.container,'6379/tcp'], text=True).strip()
            self.port = int(published.rsplit(':',1)[1])
            self.url = f'redis://127.0.0.1:{self.port}/0'
        else:
            subprocess.run(['docker','start',self.container], check=True, capture_output=True)
        client = redis.Redis.from_url(self.url, socket_timeout=.1)
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            try:
                if client.ping():
                    self.version = client.info('server')['redis_version']
                    client.close()
                    return self
            except redis.RedisError:
                time.sleep(.01)
        raise RuntimeError('Disposable container Redis startup timeout')

    def stop(self):
        if self.container:
            subprocess.run(['docker','stop','-t','1',self.container], check=True, capture_output=True)
            return
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        if self.log:
            self.log.close()
        self.process = None

    def close(self):
        self.stop()
        if self.container:
            subprocess.run(['docker','rm',self.container], check=True, capture_output=True)
            self.container = None
        self.directory.cleanup()

    def __enter__(self):
        try:
            return self.start()
        except BaseException:
            self.close()
            raise

    def __exit__(self, *exc):
        self.close()
