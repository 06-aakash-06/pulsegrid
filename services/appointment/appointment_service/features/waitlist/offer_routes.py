"""Authenticated offer commands; owner eligibility is checked before locking."""
from fastapi import Depends, Request, Query
from sqlalchemy import select
from ... import models as m, operations as op
from ...wire import ID, Input
from ...api.router import early_replay, patient_status, doctor_identity
from . import offers, operations as w


class Empty(Input):
    pass


def register_offer_routes(router, core):
    prefix = '/api/v1/appointments/waitlist-offers'

    @router.get(prefix)
    async def listing(request: Request, patient_id: ID | None = None,
                      cursor: ID | None = None, limit: int = Query(20, ge=1, le=100),
                      p=Depends(core.authenticated_user)):
        core.query_keys(request, ('patient_id', 'cursor', 'limit'))
        role = await core.authorize(request, p, ('patient', 'receptionist'))
        if role == 'patient':
            if not p.patient_id or patient_id and patient_id != p.patient_id:
                op.fail('not_found', 404)
            patient_id = p.patient_id
        conditions = [m.waitlist_offers.c.id > int(cursor or '0')]
        if patient_id:
            conditions.append(m.waitlist_offers.c.patient_id == int(patient_id))
        async with core.session_factory(request)() as session, session.begin():
            rows = (await session.execute(select(m.waitlist_offers).where(*conditions)
                .order_by(m.waitlist_offers.c.id).limit(limit + 1))).mappings().all()
            await op.audit(session, request, p, 'read', p.user_id)
        return core.response(200, {'items': [offers.view(r) for r in rows[:limit]],
            'next_cursor': str(rows[limit-1]['id']) if len(rows) > limit else None})

    async def stored(request, p, offer_id):
        async with core.session_factory(request)() as session:
            row = await op.row(session, m.waitlist_offers, offer_id)
        w.scope(p, row, None, True)
        return row

    @router.get(prefix + '/{offer_id}')
    async def detail(request: Request, offer_id: ID, p=Depends(core.authenticated_user)):
        core.query_keys(request, ())
        await core.authorize(request, p, ('patient', 'receptionist'))
        row = await stored(request, p, offer_id)
        async with core.session_factory(request)() as session, session.begin():
            await op.audit(session, request, p, 'read', offer_id)
        return core.response(200, offers.view(row))

    async def decision(request, p, offer_id, body, accept):
        await core.authorize(request, p, ('patient', 'receptionist'))
        row = await stored(request, p, offer_id)
        _, _, replay = await early_replay(request, p, body.model_dump())
        if replay:
            return core.response(*replay)
        expected = core.precondition(request.headers.get('If-Match'))
        identity = None
        if accept:
            await patient_status(request, p, str(row['patient_id']))
            identity = await doctor_identity(request, p, row['slot_id'])
        from ...integration import create_episode
        return await core.execute(request, p, body.model_dump(), lambda session:
            offers.decide(session, request, p, offer_id, expected, accept, identity, create_episode))

    @router.post(prefix + '/{offer_id}/accept')
    async def accept(request: Request, offer_id: ID, body: Empty, p=Depends(core.authenticated_user)):
        return await decision(request, p, offer_id, body, True)

    @router.post(prefix + '/{offer_id}/decline')
    async def decline(request: Request, offer_id: ID, body: Empty, p=Depends(core.authenticated_user)):
        return await decision(request, p, offer_id, body, False)
