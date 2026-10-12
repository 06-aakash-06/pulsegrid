"""One dedicated session per process; never reconnect after session loss."""
import asyncio
import psycopg
from . import IdUnavailable, Reservation


class PostgresWorkerStore:
    def __init__(self, owner_dsn: str, *, timeout_ms: int = 2000):
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 2000:
            raise ValueError("invalid store deadline")
        self._dsn, self._timeout = owner_dsn, timeout_ms
        self._connection = None
        self._worker = None
        self._lock = asyncio.Lock()
        self.reservations = 0

    async def open(self, worker_id):
        if type(worker_id) is not int or not 0 <= worker_id <= 1023:
            raise IdUnavailable("invalid_worker")
        if self._connection is not None:
            raise IdUnavailable("already_open")
        try:
            async with asyncio.timeout(self._timeout / 1000):
                self._connection = await psycopg.AsyncConnection.connect(self._dsn, autocommit=True)
                await self._connection.execute("SELECT set_config('statement_timeout', %s, false)", (str(self._timeout),))
                row = await (await self._connection.execute(
                    "SELECT pg_try_advisory_lock(74104, %s)", (worker_id,))).fetchone()
                if not row[0]:
                    raise IdUnavailable("worker_conflict")
                self._worker = worker_id
        except BaseException:
            await self.close()
            raise

    async def assert_owned(self, worker_id):
        if worker_id != self._worker or self._connection is None or self._connection.closed:
            raise IdUnavailable("ownership_lost")
        row = await (await self._connection.execute("""
            SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype='advisory'
            AND pid=pg_backend_pid() AND classid=74104 AND objid=%s
            AND objsubid=2 AND granted)
            """, (worker_id,))).fetchone()
        if not row[0]:
            raise IdUnavailable("ownership_lost")

    async def reserve(self, worker_id, now_ms, span_ms):
        if type(now_ms) is not int or now_ms < 0 or type(span_ms) is not int or not 1 <= span_ms <= 1000:
            raise IdUnavailable("invalid_reservation")
        async with self._lock:
            async with asyncio.timeout(self._timeout / 1000):
                await self.assert_owned(worker_id)
                async with self._connection.transaction():
                    row = await (await self._connection.execute("""
                        INSERT INTO id_worker_state(worker_id, reserved_through_ms)
                        VALUES (%s, %s) ON CONFLICT(worker_id) DO UPDATE
                        SET reserved_through_ms=GREATEST(%s, id_worker_state.reserved_through_ms+1)+%s-1
                        RETURNING reserved_through_ms
                        """, (worker_id, now_ms + span_ms - 1, now_ms, span_ms))).fetchone()
                self.reservations += 1
                return Reservation(row[0] - span_ms + 1, row[0])

    async def close(self):
        connection, self._connection = self._connection, None
        self._worker = None
        if connection is not None:
            await connection.close()
