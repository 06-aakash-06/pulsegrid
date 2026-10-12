"""Transport failures trip the owner circuit; missing resources do not."""
import asyncio
from types import SimpleNamespace
import httpx
import pytest
from appointment_service.features.journey import snapshots


def test_unknown_consultation_does_not_block_healthy_owner(monkeypatch):
    monkeypatch.setattr(snapshots,'service_token',lambda *args:'synthetic-test-only')
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(auth_config=None)),
        state=SimpleNamespace(request_id='test',correlation_id='test'))
    count=0
    def owner(req):
        nonlocal count
        count+=1
        return httpx.Response(404 if count<=8 else 200,json={} if count<=8 else {'revision':1})
    client=snapshots.SnapshotClient(httpx.MockTransport(owner))
    async def check():
        for _ in range(8):
            with pytest.raises(snapshots.SnapshotUnknown):
                await client.request(request,'records','workflow:records-read','/synthetic')
        assert client.breakers['records'].state=='CLOSED'
        assert await client.request(request,'records','workflow:records-read','/synthetic')=={'revision':1}
        assert count==9
        await client.close()
    asyncio.run(check())
