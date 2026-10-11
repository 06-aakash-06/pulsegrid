"""Read-only owner schema/isolation/health and activated Phase 3 route checks."""
import json
import httpx
import verify_phase2_infrastructure as baseline


def main():
    baseline.main()
    routes={
        'appointment':{
            ('POST','/api/v1/appointments/waitlists'),
            ('GET','/api/v1/appointments/waitlist-offers'),
            ('POST','/api/v1/appointments/waitlist-offers/{offer_id}/accept'),
            ('POST','/api/v1/appointments/waitlist-offers/{offer_id}/decline'),
            ('GET','/api/v1/appointments/{appointment_id}/workflow'),
            ('POST','/api/v1/appointments/{appointment_id}/check-in-links'),
            ('POST','/api/v1/appointments/{appointment_id}/check-in'),
            ('POST','/api/v1/appointments/{appointment_id}/staff-check-in'),
            ('POST','/api/v1/appointments/{appointment_id}/no-show'),
            ('GET','/api/v1/appointments/queues'),
            ('POST','/api/v1/appointments/queue-entries/{entry_id}/start'),
            ('POST','/api/v1/appointments/queue-entries/{entry_id}/skip'),
            ('POST','/api/v1/appointments/queue-entries/{entry_id}/recall'),
            ('GET','/api/v1/appointments/queue-entries/{entry_id}/history'),
            ('GET','/api/v1/appointments/journeys'),
            ('GET','/api/v1/appointments/journeys/{journey_id}'),
            ('GET','/api/v1/appointments/journeys/{journey_id}/history'),
            ('POST','/api/v1/appointments/journeys/{journey_id}/reconcile'),
            ('POST','/api/v1/appointments/journeys/{journey_id}/discharge'),
            ('GET','/internal/v1/appointments/{appointment_id}/workflow-context'),
        },
        'patient':{('POST','/internal/v1/patients/waitlist-eligibility')},
        'records':{('GET','/internal/v1/appointments/{appointment_id}/workflow-snapshot')},
        'pharmacy':{('GET','/internal/v1/appointments/{appointment_id}/workflow-snapshot')},
        'billing':{('GET','/internal/v1/appointments/{appointment_id}/workflow-snapshot')},
    }
    for domain,expected in routes.items():
        code=f'''import json
from {domain}_service.main import app
routes={{(method.upper(),path) for path,spec in app.openapi()['paths'].items() for method in spec if method.upper() in ('GET','POST','PATCH','DELETE')}}
print(json.dumps(sorted(routes)))
'''
        actual={tuple(item) for item in json.loads(baseline.compose('exec','-T',domain,'python','-',code=code))}
        assert expected<=actual,(domain,expected-actual)
        print('PASS',domain,len(expected),'reviewed Phase3 producer routes')
    result=baseline.compose('exec','-T','appointment','python','-',code='''from appointment_service.main import app
assert app.state.phase3_enabled
assert set(app.state.appointment_extensions)=={'waitlist','checkin','queue','journey'}
print('PASS all four reviewed Appointment extensions activated')
''')
    print(result)
    for path in ('/internal/v1/patients/waitlist-eligibility','/internal/v1/appointments/1/workflow-context','/internal/v1/appointments/1/workflow-snapshot'):
        assert httpx.get('http://127.0.0.1:8080'+path,trust_env=False).status_code==404
    print('PASS Phase3 private leaves remain unreachable through gateway')


if __name__=='__main__':main()
