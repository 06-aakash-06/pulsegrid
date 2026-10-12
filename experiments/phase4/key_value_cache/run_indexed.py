#!/usr/bin/env python3
"""Existing Doctor query-index sensitivity; independent disposable resources."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import fixtures
import run

# Copy query-relevant indexes from retained Doctor 0001/0004 migrations.
# No migration or shared schema is changed; this fixture is still not an HTTP API.
INDEX_DDL = [
    'CREATE INDEX ix_doctors_active ON doctors(active)',
    'CREATE INDEX ix_doctors_name_prefix ON doctors(display_name varchar_pattern_ops)',
    'CREATE INDEX ix_doctors_created_id ON doctors(created_at,id)',
    'CREATE INDEX ix_doctors_active_created_id ON doctors(active,created_at,id)',
    'CREATE INDEX ix_doctors_lower_display_name_prefix ON doctors(lower(display_name) text_pattern_ops)',
    'CREATE INDEX ix_doctor_specialties_specialty_id_doctor_id ON doctor_specialties(specialty_id,doctor_id)',
]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=404)
    parser.add_argument('--level', choices=['low','medium','high'], required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--warmup', type=float, default=.2)
    parser.add_argument('--duration', type=float, default=3)
    args = parser.parse_args()
    if not 3 <= args.duration <= 30 or not 0 <= args.warmup <= 5:
        parser.error('duration3..30 warmup0..5')
    fixtures.DDL.extend(INDEX_DDL)
    asyncio.run(run.main(args))
    path = Path(args.output)
    manifest = json.loads((path/'manifest.json').read_text())
    manifest['query_indexes'] = INDEX_DDL
    manifest['source_hashes'][str(Path(__file__))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['limitations'].append('Indexed sensitivity defaults to0.2s warmup/3s measurement; not the frozen5s/30s duration unless explicitly requested.')
    (path/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (path/'report.md').open('a') as output:
        output.write('\nExisting Doctor query-relevant secondary indexes included (see manifest). This short sensitivity run is not frozen-duration HTTP acceptance.\n')
