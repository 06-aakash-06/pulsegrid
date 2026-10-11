"""Real PostgreSQL offer/accept/expiry races, with separate owner transactions."""
import asyncio
from datetime import timedelta
from sqlalchemy import select, update
from fastapi import HTTPException
from appointment_service import models as m, phase3_core as core, operations as op
from appointment_service.integration import create_episode
from appointment_service.features.waitlist import offers
from .test_waitlist import enroll, prepared
from ..test_concurrency import run, booking, mutation, request, patient, identity


async def offer(db, prep=None):
    prep = prep or await prepared(db)
    r = request('/worker/offers'); ident, fp = op.idempotency(r, patient(), {})
    async def work(session):
        ctx = await core.lock_context(session, r, core.worker_actor(), core.LockPlan(
            waitlist_slot_ids=(1,), waitlist_patient_ids=prep.patient_ids, promotion_slot_ids=(1,)))
        row = await offers.promote(session, ctx, prep)
        return 200, offers.view(row) if row else {}
    return await core.command(db.session_factory, ident, fp, work)


async def decide(db, row, accept=True, pid='12', r=None):
    r = r or request('/offers/accept' if accept else '/offers/decline', row['version'])
    p = patient(pid); ident, fp = op.idempotency(r, p, {})
    try:
        return await core.command(db.session_factory, ident, fp, lambda session:
            offers.decide(session, r, p, row['id'], row['version'], accept, identity(), create_episode))
    except HTTPException as exc:
        return exc.status_code, exc.detail


async def setup(db):
    _, a = await booking(db)
    await enroll(db, '12'); await enroll(db, '13')
    await mutation(db, a['id'], 'cancel')
    return (await offer(db))[1]


def test_competing_accepts_and_same_key_replay(database):
    async def work(db):
        row = await setup(db)
        results = await asyncio.gather(*(decide(db, row) for _ in range(12)))
        assert sum(code == 200 for code, _ in results) == 1
        assert all(code in (200, 412) for code, _ in results)
        async with db.session_factory() as session:
            bookings = (await session.execute(select(m.appointments).where(
                m.appointments.c.state == 'confirmed', m.appointments.c.slot_id == 1))).mappings().all()
            assert len(bookings) == 1 and bookings[0]['patient_id'] == 12
            assert len((await session.execute(select(m.appointment_workflows))).all()) == 1
            assert len((await session.execute(select(m.journey_stages))).all()) == 6
        # Replaying the winning command is separately exercised with an identical key.
    run(database, work)


def test_decline_and_durable_expiry_choose_next_fifo(database):
    async def work(db):
        row = await setup(db)
        assert (await decide(db, row, False))[0] == 200
        successor = (await offer(db))[1]
        assert successor['patient_id'] == '13'
        async with db.session_factory() as session, session.begin():
            await session.execute(update(m.waitlist_offers).where(m.waitlist_offers.c.id == int(successor['id']))
                .values(expires_at=op.now() - timedelta(seconds=1)))
        assert (await decide(db, successor, pid='13')) == (409, 'offer_unavailable')
        assert (await offer(db))[1] == {}
        async with db.session_factory() as session:
            final = await op.row(session, m.waitlist_offers, successor['id'])
            assert final['state'] == 'expired'
            row = await op.row(session, m.waitlist_entries, successor['entry_id'])
            assert row['state'] == 'skipped' and row['skip_reason'] == 'offer_expired'
    run(database, work)


def test_expiry_accept_race_and_scope(database):
    async def work(db):
        row = await setup(db)
        assert await decide(db, row, pid='13') == (404, 'not_found')
        async with db.session_factory() as session, session.begin():
            await session.execute(update(m.waitlist_offers).where(m.waitlist_offers.c.id == int(row['id']))
                .values(expires_at=op.now() - timedelta(seconds=1)))
        prep = await prepared(db)
        outcomes = await asyncio.gather(decide(db, row), offer(db, prep), offer(db, prep), return_exceptions=True)
        assert outcomes[0][0] in (409, 412)
        async with db.session_factory() as session:
            pending = (await session.execute(select(m.waitlist_offers).where(m.waitlist_offers.c.state == 'pending'))).mappings().all()
            assert len(pending) == 1 and pending[0]['patient_id'] == 13
            assert not (await session.execute(select(m.appointments).where(m.appointments.c.state == 'confirmed'))).all()
    run(database, work)


def test_reservation_rejects_direct_booking_and_accept_replays(database):
    from sqlalchemy import insert
    from sqlalchemy.exc import DBAPIError
    async def work(db):
        row = await setup(db)
        async with db.session_factory() as session:
            slot = await op.row(session, m.slots, 1)
        try:
            async with db.session_factory() as session, session.begin():
                await session.execute(insert(m.appointments).values(id=op.new_id(),patient_id=99,
                    slot_id=1,doctor_id=1,doctor_user_id=101,starts_at=slot['starts_at'],
                    ends_at=slot['ends_at'],schedule_revision=1,state='confirmed'))
        except DBAPIError as exc:
            assert getattr(exc.orig, 'sqlstate', None) == '23514'
        else:
            raise AssertionError('Database must protect offered capacity')
        r = request('/offers/accept', 1)
        result = await decide(db, row, r=r)
        assert result[0] == 200
        assert await decide(db, row, r=r) == result
    run(database, work)
