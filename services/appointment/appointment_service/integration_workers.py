"""Bounded scheduler, backed by durable owner leases rather than memory timers."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4
from .features.waitlist import worker as waitlist, offers
from .features.journey import worker as journey


def worker_request(app):
    return SimpleNamespace(app=app,state=SimpleNamespace(request_id=uuid4(),correlation_id=uuid4(),traceparent=None))


async def worker_loop(app):
    factory=app.state.database.session_factory
    async def fetch(ids):
        return await app.state.snapshot_client.request(worker_request(app),'patient','patients:waitlist-eligibility',
            '/internal/v1/patients/waitlist-eligibility','POST',{'patient_ids':ids})
    while True:
        try:
            await waitlist.repair(factory)
            for _ in range(20):
                if not await waitlist.run_once(factory,worker_request(app),fetch,promotion_policy=offers.promote):break
            for _ in range(20):
                if not await journey.run_once(factory,worker_request(app)):break
        except asyncio.CancelledError:raise
        except Exception:
            # Secrets/source payloads are never logged. Leases/backoff recover.
            app.state.logger.warning('phase3_worker_retry')
        await asyncio.sleep(5)
