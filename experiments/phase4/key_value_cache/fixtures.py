"""Owned disposable storage and seeded synthetic Doctor projection fixtures."""
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@contextmanager
def storage(node_count=2):
    if not 1 <= node_count <= 4: raise ValueError("bounded disposable topology")
    with tempfile.TemporaryDirectory(prefix='pulsegrid-cache-') as temp:
        root = Path(temp); port = free_port(); redis_ports = [free_port() for _ in range(node_count)]
        subprocess.run(['initdb', '-D', str(root/'db'), '--auth=trust', '--encoding=UTF8', '--no-locale'], check=True, stdout=subprocess.DEVNULL)
        processes = []
        db_started = False
        try:
            subprocess.run(['pg_ctl', '-D', str(root/'db'), '-l', str(root/'postgres.log'), '-o', f'-h 127.0.0.1 -p {port} -k {temp}', '-w', 'start'], check=True, stdout=subprocess.DEVNULL)
            db_started = True
            for index, rp in enumerate(redis_ports):
                rd = root/f'redis{index}'; rd.mkdir()
                processes.append(subprocess.Popen(['redis-server', '--bind', '127.0.0.1', '--port', str(rp), '--dir', str(rd), '--save', '', '--appendonly', 'no'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1', rp), timeout=.05): break
                    except OSError: time.sleep(.02)
                else: raise RuntimeError('Redis startup failed')
            yield f'postgresql+psycopg://@127.0.0.1:{port}/postgres', redis_ports, processes
        finally:
            for p in processes:
                if p.poll() is None: p.terminate()
                p.wait(timeout=5)
            if db_started:
                subprocess.run(['pg_ctl', '-D', str(root/'db'), '-m', 'fast', '-w', 'stop'], check=True, stdout=subprocess.DEVNULL)


DDL = [
    'CREATE TABLE directory_revision(singleton boolean PRIMARY KEY CHECK(singleton), revision bigint NOT NULL CHECK(revision>=1))',
    'INSERT INTO directory_revision VALUES(true,1)',
    '''CREATE TABLE doctors(id bigint PRIMARY KEY, display_name text NOT NULL, active boolean NOT NULL,
       created_at timestamptz NOT NULL, staff_user_id bigint, profile_version bigint DEFAULT 1,
       version bigint DEFAULT 1, updated_at timestamptz DEFAULT now())''',
    'CREATE TABLE specialties(id bigint PRIMARY KEY, name text NOT NULL)',
    'CREATE TABLE doctor_specialties(doctor_id bigint REFERENCES doctors(id),specialty_id bigint REFERENCES specialties(id),PRIMARY KEY(doctor_id,specialty_id))',
]


async def seed(engine, rows):
    from sqlalchemy import text
    async with engine.begin() as conn:
        for sql in DDL: await conn.execute(text(sql))
        await conn.execute(text("INSERT INTO specialties SELECT i,'Specialty '||i FROM generate_series(1,10) i"))
        await conn.execute(text("INSERT INTO doctors(id,display_name,active,created_at,staff_user_id) SELECT i,'Synthetic doctor '||lpad(i::text,6,'0'),true,'2026-01-01'::timestamptz + i*interval '1 second',i FROM generate_series(1,:rows) i"), {'rows': rows})
        await conn.execute(text('INSERT INTO doctor_specialties SELECT i,1+i%10 FROM generate_series(1,:rows) i'), {'rows': rows})
