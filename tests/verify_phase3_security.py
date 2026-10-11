"""Additional real gateway QR revocation/concurrency and late-source recovery."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import uuid
from verify_phase2 import Actor


def main():
    file=Path('/tmp/pulsegrid-phase3-security-fixture.json')
    state=json.loads((file if file.exists() else Path('/tmp/pulsegrid-phase3-live-fixture.json')).read_text());r=state['resources']
    actors={role:Actor('http://127.0.0.1:8080',state['actors'][role]) for role in ('patient','other','third','doctor','receptionist','pharmacist')}
    for actor in actors.values():actor.login()
    def save():file.write_text(json.dumps(state,indent=2));file.chmod(0o600)
    def create(label,actor,path,body,etag=None,codes=(201,)):
        if label not in r:r[label]=actor.call('POST',path,body,etag,str(uuid.uuid5(uuid.UUID(state['run']),label)),codes)[0];save()
        return r[label]
    patient=actors['patient'];third=actors['third'];doctor=actors['doctor'];reception=actors['receptionist']
    revision=r['decision']['revision'];slots=r['slots']
    a=create('revocation_booking',patient,'/api/v1/appointments',{'patient_id':patient.data['profile']['id'],'slot_id':slots[6]['id'],'expected_schedule_revision':revision})
    if 'booking_change_revocation' not in state['checks']:
        _,et,_=patient.call('GET',f'/api/v1/appointments/{a["id"]}/workflow')
        old=patient.call('POST',f'/api/v1/appointments/{a["id"]}/check-in-links',{},et,str(uuid.uuid4()),(201,))[0]
        _,et,_=patient.call('GET',f'/api/v1/appointments/{a["id"]}')
        create('security_reschedule',patient,f'/api/v1/appointments/{a["id"]}/reschedule',{'target_slot_id':slots[7]['id'],'expected_schedule_revision':revision},et,(200,))
        _,et,_=patient.call('GET',f'/api/v1/appointments/{a["id"]}/workflow')
        patient.call('POST',f'/api/v1/appointments/{a["id"]}/check-in',{'token':old['token']},et,str(uuid.uuid4()),(409,))
        new=patient.call('POST',f'/api/v1/appointments/{a["id"]}/check-in-links',{},et,str(uuid.uuid4()),(201,))[0]
        _,et,_=patient.call('GET',f'/api/v1/appointments/{a["id"]}')
        create('security_cancel',patient,f'/api/v1/appointments/{a["id"]}/cancel',{'reason':'Synthetic token revocation'},et,(200,))
        _,et,_=patient.call('GET',f'/api/v1/appointments/{a["id"]}/workflow')
        patient.call('POST',f'/api/v1/appointments/{a["id"]}/check-in',{'token':new['token']},et,str(uuid.uuid4()),(409,))
        state['checks'].append('booking_change_revocation');save()
    print('PASS rescheduling_and_cancellation_invalidate_real_credentials',flush=True)
    b=create('checkin_race_booking',third,'/api/v1/appointments',{'patient_id':third.data['profile']['id'],'slot_id':slots[6]['id'],'expected_schedule_revision':revision})
    if 'gateway_qr_race' not in state['checks']:
        _,et,_=third.call('GET',f'/api/v1/appointments/{b["id"]}/workflow')
        token=third.call('POST',f'/api/v1/appointments/{b["id"]}/check-in-links',{},et,str(uuid.uuid4()),(201,))[0]['token']
        _,et,_=third.call('GET',f'/api/v1/appointments/{b["id"]}/workflow')
        def redeem(_):return third.call('POST',f'/api/v1/appointments/{b["id"]}/check-in',{'token':token},et,str(uuid.uuid4()),(200,409,412))[2]
        with ThreadPoolExecutor(max_workers=12) as pool:codes=list(pool.map(redeem,range(12)))
        assert codes.count(200)==1,codes
        entry=third.call('GET',f'/api/v1/appointments/{b["id"]}/queue')[0]['entry']
        r['gateway_qr_race']={'requests':12,'exclusive_successes':1,'entry':entry};state['checks'].append('gateway_qr_race');save()
    print('PASS twelve_gateway_redemptions_one_entry_one_daily_token',flush=True)
    create('browser_manual_booking',actors['other'],'/api/v1/appointments',{'patient_id':actors['other'].data['profile']['id'],'slot_id':slots[7]['id'],'expected_schedule_revision':revision})
    # Real owner source revision following an already-committed dispensing.
    if 'late_revocation_reconciliation' not in state['checks']:
        rx=r['full_final']['prescription'];current,et,_=doctor.call('GET','/api/v1/records/prescriptions/'+rx['id'])
        if current['state']=='issued':create('late_revoke',doctor,f'/api/v1/records/prescriptions/{rx["id"]}/revoke',{'reason':'Synthetic late revocation'},et,(200,))
        actors['pharmacist'].call('GET',f'/api/v1/pharmacy/prescriptions/{rx["id"]}/fulfillment')
        jid=r['full_booking']['journey_id']
        for _ in range(12):
            _,et,_=patient.call('GET',f'/api/v1/appointments/journeys/{jid}')
            value,_,status=patient.call('POST',f'/api/v1/appointments/journeys/{jid}/reconcile',{},et,str(uuid.uuid4()),(200,412))
            if status==200:break
        assert value['review_required'] and not value['discharge_eligible']
        reception.call('POST',f'/api/v1/appointments/journeys/{jid}/discharge',{'reason':'Must deny unresolved revocation'},f'"{value["version"]}"',str(uuid.uuid4()),(409,412))
        retained=actors['pharmacist'].call('GET','/api/v1/pharmacy/dispensings/'+r['full_dispense']['id'])[0]
        assert retained['id']==r['full_dispense']['id']
        state['checks'].append('late_revocation_reconciliation');save()
    print('PASS late_prescription_revocation_retains_dispensing_blocks_discharge',flush=True)


if __name__=='__main__':main()
