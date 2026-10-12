"""Measured deterministic rollback/restart timeline against disposable owner DB."""
import asyncio
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'components/unique_id'))
from pulsegrid_unique_id import Config, Generator, PostgresWorkerStore, EPOCH_MS, IdUnavailable
from fixture import DeterministicClock

async def main():
    clock=DeterministicClock(EPOCH_MS+10000)
    g=Generator(Config(800),PostgresWorkerStore(os.environ['ID_TEST_DSN']),clock=clock,sleep=clock.sleep)
    events=[]
    def record(event, **data): events.append(dict(event=event,clock_ms=clock(),**data))
    try:
        await g.start(); record('range_committed',start_ms=g._range.start_ms,end_ms=g._range.end_ms)
        value=await g.next_id(); record('issued',value=str(value))
        clock.now_ms-=1
        try: await g.next_id()
        except IdUnavailable as exc: record('rollback_rejected',reason=str(exc))
        else: raise AssertionError('rollback accepted')
        old_end=g._range.end_ms
        await g.close(); record('closed')
        await g.start(); record('restart_reserved',start_ms=g._range.start_ms,end_ms=g._range.end_ms)
        before=clock()
        replacement=await g.next_id()
        record('restart_issued',value=str(replacement),restart_wait_ms=clock()-before)
        assert g.decode(replacement)['timestamp_ms']>old_end
    finally: await g.close()
    path=Path('experiments/phase4/unique_id/results/boundaries')
    path.mkdir(parents=True,exist_ok=True)
    (path/'timeline.json').write_text(json.dumps(events,indent=2)+'\n')
    print(json.dumps(events))

asyncio.run(main())
