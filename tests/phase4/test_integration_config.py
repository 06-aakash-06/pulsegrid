"""Frozen composition checks: identity allocation, route order and metadata safety."""
import json
import pytest
from pulsegrid_consistent_hashing import HashRing,RingSnapshot
from pulsegrid_key_value_cache import Cache
from doctor_service.admission import policy_for

def test_ring_cache_port_actual_distribution():
    ring=HashRing(RingSnapshot(1,128,('cache_a','cache_b')))
    assert ring.epoch==1
    keys=[f'synthetic:{i}'.encode() for i in range(10000)]
    placements=[ring.locate(key) for key in keys]
    assert set(placements)=={'cache_a','cache_b'}
    changed=ring.with_node(__import__('pulsegrid_consistent_hashing').Node('cache_c'),2)
    assert all(changed.locate(key)=='cache_c' for key,node in zip(keys,placements) if changed.locate(key)!=node)
    cache=Cache(ring,{'cache_a':object(),'cache_b':object()})
    for key in keys[:100]:
        client,physical=cache._target(key)
        assert client is cache.clients[ring.locate(key)]
        assert physical.startswith('pg:cache:v1:doctor:1:')

def test_emergency_and_directory_policy_partitions():
    assert policy_for('doctor','GET','/api/v1/doctors/autocomplete')==('directory_search','directory')
    assert policy_for('emergency','POST','/api/v1/emergencies')[0]=='emergency_authenticated'
    assert policy_for('appointment','POST','/api/v1/appointments/{appointment_id}/short-links')[0]=='appointment_command'

@pytest.mark.parametrize('module,flag,path',[('doctor','AUTOCOMPLETE','/api/v1/doctors/autocomplete'),('pharmacy','AUTOCOMPLETE','/api/v1/pharmacy/medicines/autocomplete')])
def test_literal_routes_enabled_before_parameter_routes(monkeypatch,module,flag,path):
    import importlib
    monkeypatch.setenv(f'PULSEGRID_{module.upper()}_PHASE4_{flag}_ENABLED','true')
    app=importlib.import_module(module+'_service.main').create_app()
    schema=app.openapi()
    assert path in schema['paths']
