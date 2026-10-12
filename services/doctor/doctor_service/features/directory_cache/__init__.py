"""Unmounted Doctor-only projection adapter. Authentication precedes this port."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from sqlalchemy import text
from pulsegrid_key_value_cache import CacheEntry, InvalidEntry, canonical_json, logical_key


@dataclass(frozen=True)
class DirectoryFilters:
    tenant: str
    role: str
    query: str | None = None
    specialty_id: str | None = None
    cursor: tuple[datetime, str] | None = None
    limit: int = 20

    def __post_init__(self):
        if not self.tenant or len(self.tenant) > 64 or self.role not in {
            'patient', 'doctor', 'receptionist', 'hospital_admin', 'pharmacist', 'billing_staff', 'emergency_staff', 'ops'}:
            raise ValueError('invalid visibility partition')
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError('invalid limit')
        if self.query is not None and (not 2 <= len(self.query) <= 100 or self.query != self.query.strip().lower()):
            raise ValueError('use existing owner normalized_search before adapter')
        if self.specialty_id is not None:
            _id(self.specialty_id)
        if self.cursor:
            if self.cursor[0].tzinfo is None:
                raise ValueError('cursor must be UTC aware')
            _id(self.cursor[1])

    def key(self, revision):
        cursor = None if self.cursor is None else [self.cursor[0].astimezone(timezone.utc).isoformat(), self.cursor[1]]
        return logical_key(owner='doctor', schema=1,
                           visibility={'tenant': self.tenant, 'role': self.role, 'active': 'true'},
                           revision=revision, filters=dict(query=self.query, specialty_id=self.specialty_id,
                                                           cursor=cursor, limit=self.limit))


def _id(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or value.startswith('0') or not 1 <= int(value) <= 9223372036854775807:
        raise InvalidEntry('invalid ID')


def validate_projection(payload):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise InvalidEntry('duplicate field')
            value[key] = item
        return value
    try:
        value = json.loads(payload, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != {'schema_version', 'items', 'next_cursor'} or type(value['schema_version']) is not int or value['schema_version'] != 1:
            raise InvalidEntry('projection schema')
        if not isinstance(value['items'], list) or len(value['items']) > 100:
            raise InvalidEntry('projection bounds')
        if value['next_cursor'] is not None and (not isinstance(value['next_cursor'], str) or len(value['next_cursor']) > 1024):
            raise InvalidEntry('cursor bounds')
        if len({item['id'] for item in value['items']})!=len(value['items']):raise InvalidEntry('duplicate source entity')
        for item in value['items']:
            if set(item) != {'id', 'display_name', 'specialties'}:
                raise InvalidEntry('sensitive or unexpected field')
            _id(item['id'])
            if not isinstance(item['display_name'], str) or not 1 <= len(item['display_name']) <= 200 or not isinstance(item['specialties'], list) or len(item['specialties']) > 20:
                raise InvalidEntry('projection bounds')
            for specialty in item['specialties']:
                if set(specialty) != {'id', 'name'}:
                    raise InvalidEntry('specialty shape')
                _id(specialty['id'])
                if not isinstance(specialty['name'], str) or not 1 <= len(specialty['name']) <= 200:
                    raise InvalidEntry('specialty bounds')
        return value
    except (TypeError, KeyError, ValueError, UnicodeError):
        raise InvalidEntry('invalid projection') from None


async def read_revision(session) -> int:
    revision = (await session.execute(text('SELECT revision FROM directory_revision WHERE singleton=true'))).scalar_one()
    if type(revision) is not int or not 1 <= revision <= 9007199254740991:
        raise InvalidEntry('invalid owner revision')
    return revision


async def load_projection(session, filters: DirectoryFilters):
    """One PostgreSQL statement snapshot includes projection AND revision.

    No DB locks and no Redis I/O. Owner supplies its bounded session/transaction.
    Returns (revision, payload bytes); owner wire fields must be reconstructed live.
    """
    conditions = ['d.active=true']
    params = {'limit': filters.limit + 1}
    if filters.query is not None:
        conditions.append("lower(d.display_name) LIKE :query ESCAPE '!'")
        params['query'] = filters.query.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
    if filters.specialty_id:
        conditions.append('EXISTS (SELECT 1 FROM doctor_specialties x WHERE x.doctor_id=d.id AND x.specialty_id=:specialty)')
        params['specialty'] = int(filters.specialty_id)
    if filters.cursor:
        conditions.append('(d.created_at,d.id) > (:created_at,:id)')
        params.update(created_at=filters.cursor[0], id=int(filters.cursor[1]))
    statement = '''SELECT r.revision, COALESCE((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.created_at,p.id::bigint)
        FROM (SELECT d.id::text AS id,d.display_name,d.created_at,
        COALESCE((SELECT jsonb_agg(jsonb_build_object('id',s.id::text,'name',s.name) ORDER BY s.id)
        FROM doctor_specialties ds JOIN specialties s ON s.id=ds.specialty_id
        WHERE ds.doctor_id=d.id),'[]'::jsonb) AS specialties
        FROM doctors d WHERE ''' + ' AND '.join(conditions) + '''
        ORDER BY d.created_at,d.id LIMIT :limit) p),'[]'::jsonb) AS items
        FROM directory_revision r WHERE singleton=true'''
    row = (await session.execute(text(statement), params)).mappings().one()
    if type(row['revision']) is not int or not 1 <= row['revision'] <= 9007199254740991:
        raise InvalidEntry('invalid owner revision')
    items = row['items']
    # Preserve the owner's opaque cursor and original filter digest convention.
    next_cursor = None
    if len(items) > filters.limit:
        from ...wire import encode_cursor, filter_digest
        digest = filter_digest({'active': True, 'specialty_id': filters.specialty_id, 'q': filters.query})
        last = items[filters.limit - 1]
        next_cursor = encode_cursor(datetime.fromisoformat(last['created_at'].replace('Z', '+00:00')), last['id'], digest)
    payload = canonical_json(dict(schema_version=1, items=[{k: v for k, v in item.items() if k != 'created_at'} for item in items[:filters.limit]], next_cursor=next_cursor))
    validate_projection(payload)
    return row['revision'], payload


class _RevisionRace(Exception):
    def __init__(self, projection):
        self.projection = projection


async def cache_projection(cache, revision: int, filters: DirectoryFilters, loader):
    """Caller reads current revision first. Loader returns consistent (rev, bytes).

    On revision race return fresh owner snapshot without populating requested key.
    A corrupt or mismatched hit is deleted best effort and loaded authoritatively.
    """
    key = filters.key(revision)
    async def entry_loader():
        source_revision, payload = await loader()
        projection = validate_projection(payload)
        if type(source_revision) is not int or not 1 <= source_revision <= 9007199254740991:
            raise InvalidEntry('invalid owner revision')
        if source_revision != revision:
            raise _RevisionRace(projection)
        return CacheEntry(payload, source_revision, cache.clock() + cache.ttl_ms)
    try:
        entry = await cache.get_or_load(key, entry_loader)
    except _RevisionRace as race:
        return race.projection
    try:
        projection = validate_projection(entry.payload)
        if entry.source_version != revision:
            raise InvalidEntry('owner revision mismatch')
        if len(projection['items']) > filters.limit:
            raise InvalidEntry('page bounds')
        return projection
    except InvalidEntry:
        await cache.invalidate(key)
        try:
            fresh = await entry_loader()
            return validate_projection(fresh.payload)
        except _RevisionRace as race:
            return race.projection


async def invalidate_projection(cache, revision, filters):
    return await cache.invalidate(filters.key(revision))
