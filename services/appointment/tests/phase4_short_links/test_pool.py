"""Regression: secure resolution must work with one bounded owner connection."""
import asyncio
from dataclasses import replace
from .test_short_links import _install_test_table,_enroll,_make_app,_create,_resolve,_json,ShortLinksTestPorts
from ..test_concurrency import run,patient

def test_concurrent_resolution_never_nests_pool_acquisition(database,current_authority):
    async def work(db):
        await _install_test_table(db)
        aid=await _enroll(db)
        ports=ShortLinksTestPorts(db)
        app=_make_app(db,ports)
        response=await _create(app,aid)
        alias=_json(response)['short_path'].rsplit('/',1)[-1]
        results=await asyncio.gather(*(_resolve(app,alias,principal=patient()) for _ in range(8)))
        assert all(result.status_code==200 for result in results)
        assert db.engine.pool.checkedout()==0
    run(replace(database,db_pool_size=1,db_max_overflow=0,db_pool_timeout=.5),work)
