"""Read-only owner verification after Phase 9 browser transactions.

The private fixture is never an application data source. All assertions query
current owning APIs through the existing authenticated gateway/proxy.
"""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from verify_phase2 import Actor

def verify(base,fixture,output):
    state=json.loads(fixture.read_text());r=state['resources'];b=r['browser_results'];actors={}
    for role in ['patient','doctor','pharmacist','billing_staff','emergency_staff','admin']:
        actor=Actor(base,state['actors'][role]);actor.login();actors[role]=actor
    checks=[]
    def checked(name,valid):
        assert valid,name
        checks.append({'name':name,'status':'PASS'})
    a,_,_=actors['patient'].call('GET','/api/v1/appointments/'+b['appointment_id'])
    checked('browser booking is persisted under the correct patient and doctor',a['patient_id']==state['actors']['patient']['profile']['id'] and a['doctor_id']==r['doctor']['id'])
    workflow,_,_=actors['patient'].call('GET',f'/api/v1/appointments/{a["id"]}/workflow')
    checked('QR check-in and clinical completion are owner-confirmed',workflow['state']=='completed')
    queue,_,_=actors['patient'].call('GET',f'/api/v1/appointments/{a["id"]}/queue')
    checked('daily queue token is retained after clinical completion',queue['entry']['token_number']==1 and queue['entry']['state']=='completed')
    consult,_,_=actors['doctor'].call('GET','/api/v1/records/consultations/'+b['consultation_id'])
    checked('consultation finalization is persisted by Records',consult['status']=='finalized')
    record,_,_=actors['patient'].call('GET','/api/v1/records/'+b['record_id'])
    checked('immutable patient record references the finalized consultation',record['consultation_id']==b['consultation_id'])
    rx,_,_=actors['pharmacist'].call('GET','/api/v1/records/prescriptions/'+b['prescription_id'])
    checked('prescription retains the owner-issued medicine quantity',rx['state']=='issued' and rx['items'][0]['quantity']==2 and rx['items'][0]['medicine_id']==r['medicine']['id'])
    reservation,_,_=actors['pharmacist'].call('GET','/api/v1/pharmacy/reservations/'+b['reservation_id'])
    checked('reservation is dispensed and cannot be treated as unfulfilled',reservation['state']=='dispensed')
    invoice,_,_=actors['billing_staff'].call('GET','/api/v1/billing/invoices/'+b['invoice_id'])
    checked('Billing owns the INR 150 total and zero paid balance',invoice['status']=='paid' and invoice['currency']=='INR' and invoice['total_minor']==15000 and invoice['paid_minor']==15000 and invoice['balance_minor']==0)
    payments,_,_=actors['billing_staff'].call('GET',f'/api/v1/billing/invoices/{invoice["id"]}/payments')
    checked('committed simulated decline and success both remain in payment history',{p['status'] for p in payments['items']}=={'declined','success'})
    managed,_,_=actors['patient'].call('GET','/api/v1/appointments/'+r['management_booking']['id'])
    checked('rescheduling retained the selected slot before cancellation',managed['state']=='cancelled' and managed['slot_id']==r['slots'][3]['id'])
    emergency,_,_=actors['emergency_staff'].call('GET','/api/v1/emergencies/'+b['emergency_id'])
    checked('Emergency owner confirms resolved priority 2 and released claim',emergency['state']=='resolved' and emergency['assigned_priority']==2 and emergency['claimed_by_user_id'] is None)
    other=Actor(base,json.loads(Path('/tmp/pulsegrid-phase29-live-fixture.json').read_text())['actors']['other']);other.login()
    other.call('GET','/api/v1/appointments/'+a['id'],codes=(404,))
    other.call('GET','/api/v1/records/'+record['id'],codes=(404,))
    checked('another patient cannot read the new appointment or clinical record',True)
    actors['patient'].call('GET','/api/v1/appointments/operations/control-room/summary',codes=(403,))
    actors['patient'].call('GET','/api/v1/appointments/operations/surge-mode',codes=(403,))
    checked('patient role cannot read Control Room or admin Surge state',True)
    summary,_,_=actors['admin'].call('GET','/api/v1/appointments/operations/control-room/summary')
    checked('authorized technical summary includes all seven domains',len(summary['services'])==7)
    surge,_,_=actors['admin'].call('GET','/api/v1/appointments/operations/surge-mode')
    checked('browser review did not change global admission from NORMAL',surge['state']=='NORMAL')
    result={'status':'PASS','checks':checks,'browser_resource_ids':b,'billing_total_minor':invoice['total_minor'],'billing_balance_minor':invoice['balance_minor'],'currency':'INR','backend_code_changed':False,'database_resets':False,'physical_camera_verified':False}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS',len(checks),'current owner-state and authorization checks')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base-url',default='http://127.0.0.1:5173');p.add_argument('--fixture',type=Path,default=Path('/tmp/pulsegrid-phase9-live-fixture.json'));p.add_argument('--output',type=Path,default=ROOT/'docs/verification/phase9/live-owner-verification.json');a=p.parse_args();verify(a.base_url,a.fixture,a.output)
