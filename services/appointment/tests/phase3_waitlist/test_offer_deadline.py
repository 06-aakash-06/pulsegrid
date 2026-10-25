"""A healthy pending offer must wake by its durable deadline, not retry backoff."""
from datetime import timedelta

from sqlalchemy import text, update

from appointment_service import models as m, operations as op
from appointment_service.features.waitlist import offers, worker
from .test_offers import setup
from ..test_concurrency import run, request


def test_worker_retry_never_delays_pending_offer_expiry(database):
    async def work(db):
        offer = await setup(db)
        expiry = op.now() + timedelta(seconds=10)
        async with db.session_factory() as session, session.begin():
            await session.execute(update(m.waitlist_offers).values(expires_at=expiry))
            await session.execute(text('UPDATE promotion_jobs SET attempt_count=20, next_attempt_at=:due'),
                                  {'due': op.now() - timedelta(seconds=1)})

        async def eligible(ids):
            return {'items': [{'patient_id': pid, 'active': True, 'version': 1} for pid in ids],
                    'observed_at': op.wire_time(op.now())}

        assert await worker.run_once(db.session_factory, request(), eligible,
                                     promotion_policy=offers.promote)
        async with db.session_factory() as session:
            job = (await session.execute(text('SELECT * FROM promotion_jobs'))).mappings().one()
            assert job['next_attempt_at'] <= expiry
            assert job['lease_token'] is None
            current = await op.row(session, m.waitlist_offers, offer['id'])
            assert current['state'] == 'pending'

        async with db.session_factory() as session, session.begin():
            await session.execute(update(m.waitlist_offers).values(
                expires_at=op.now() - timedelta(seconds=1)))
            await session.execute(text('UPDATE promotion_jobs SET next_attempt_at=:due'),
                                  {'due': op.now() - timedelta(seconds=1)})
        assert await worker.run_once(db.session_factory, request(), eligible,
                                     promotion_policy=offers.promote)
        async with db.session_factory() as session:
            first = await op.row(session, m.waitlist_offers, offer['id'])
            assert first['state'] == 'expired'
            successor = await offers.pending(session, int(offer['slot_id']))
            assert successor['patient_id'] == 13

    run(database, work)
