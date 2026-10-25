"""Focused real-owner acceptance gaps, on isolated fictional fixtures only."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import json,sys,uuid,time
from prepare_acceptance import ROOT,BASE,AcceptanceActor,isolated

def main():
 isolated();fixture=ROOT/'secrets/phase10/fixture.json';state=json.loads(fixture.read_text());r=state['resources'];actors={};checks=state.setdefault('acceptance_checks',[])
 def save():fixture.write_text(json.dumps(state,indent=2));fixture.chmod(0o600)
 def checked(label):
  if label not in checks:checks.append(label)
  save();print('PASS',label,flush=True)
 def key(label):return str(uuid.uuid5(uuid.UUID(state['run']),'acceptance-'+label))
 for role in ('patient','other','third','doctor','alternate_doctor','receptionist','pharmacist','billing_staff','emergency_staff','hospital_admin','ops'):
  a=AcceptanceActor(BASE,state['actors'][role]);a.login();actors[role]=a
 p=actors['patient'];other=actors['other'];doctor=actors['doctor'];alternate=actors['alternate_doctor'];admin=actors['hospital_admin'];pharm=actors['pharmacist'];billing=actors['billing_staff'];reception=actors['receptionist']
 def create(label,actor,path,body,etag=None,codes=(201,)):
  if label not in r:r[label]=actor.call('POST',path,body,etag,key(label),codes)[0];save()
  return r[label]
 def post(actor,path,body,et=None,label=None,codes=(200,)):
  return actor.call('POST',path,body,et,key(label)if label else str(uuid.uuid4()),codes)
 if 'profile_directory_and_account_authority'not in checks:
  original,et,_=p.call('GET','/api/v1/patients/me');profile,new_et,_=p.call('PATCH','/api/v1/patients/me',{'synthetic_contact':'Fictional Phase10 acceptance contact'},et);assert profile['synthetic_contact']=='Fictional Phase10 acceptance contact'
  p.call('PATCH','/api/v1/patients/me',{'synthetic_contact':'stale write'},et,codes=(412,))
  data=reception.call('GET','/api/v1/patients?limit=100')[0];assert any(x['id']==profile['id']for x in data['items'])
  own,et,_=reception.call('GET','/api/v1/patients/'+profile['id']);updated,_,_=reception.call('PATCH','/api/v1/patients/'+profile['id'],{'synthetic_contact':'Fictional reception edit'},et);assert updated['synthetic_contact']=='Fictional reception edit'
  uid=state['actors']['third']['profile']['user_id'];u,et,_=admin.call('GET','/api/v1/patients/users/'+uid)
  blocked,et,_=admin.call('PATCH',f'/api/v1/patients/users/{uid}/account-state',{'state':'disabled','reason':'Synthetic account-state acceptance'},et)
  third=actors['third'];third.call('GET','/api/v1/patients/me',codes=(401,403))
  admin.call('PATCH',f'/api/v1/patients/users/{uid}/account-state',{'state':'active','reason':'Restore fictional test account'},et);third.login()
  checked('profile_directory_and_account_authority')
 if 'doctor_catalog_search_and_maintenance'not in checks:
  d,et,_=doctor.call('GET','/api/v1/doctors/'+r['doctor']['id']);d,_,_=doctor.call('PATCH','/api/v1/doctors/'+d['id'],{'display_name':'Phase10 Acceptance Doctor'},et)
  directory=p.call('GET','/api/v1/doctors?q=Phase10&limit=100')[0];assert any(x['id']==d['id']for x in directory['items'])
  for prefix in ('phase10','PHASE10','Phase10'):
   suggestions=p.call('GET','/api/v1/doctors/autocomplete?prefix='+prefix+'&limit=10')[0];assert suggestions
  checked('doctor_catalog_search_and_maintenance')
 if 'medicine_catalog_search_autocomplete_and_version'not in checks:
  med,et,_=pharm.call('GET','/api/v1/pharmacy/medicines/'+r['medicine']['id']);med,_,_=pharm.call('PATCH','/api/v1/pharmacy/medicines/'+med['id'],{'name':'Phase10 Synthetic Medicine Updated','active':True},et)
  p.call('PATCH','/api/v1/pharmacy/medicines/'+med['id'],{'active':False},et,codes=(403,))
  listed=p.call('GET','/api/v1/pharmacy/medicines?q=Phase10&limit=100')[0];assert any(x['id']==med['id']for x in listed['items'])
  assert p.call('GET','/api/v1/pharmacy/medicines/autocomplete?prefix=phase10&limit=10')[0]
  checked('medicine_catalog_search_autocomplete_and_version')
 # Real upcoming cases within existing check-in windows; no optical injection.
 def checkin(label):
  appointment=r[label+'_booking'];aid=appointment['id'];path='/api/v1/appointments/'+aid
  workflow,et,_=p.call('GET',path+'/workflow')
  if workflow['state']=='booked':
   if label+'_credential'not in r:
    # Credentials are private fixture data, never exported as evidence.
    r[label+'_credential']=post(p,path+'/check-in-links',{},et,label+'-issue',(201,))[0];save()
   credential=r[label+'_credential']['token'];workflow,et,_=p.call('GET',path+'/workflow');checked_in=post(p,path+'/check-in',{'token':credential},et,label+'-checkin')[0];r[label+'_checkin']=checked_in;save()
  queue,et,_=doctor.call('GET',path+'/queue')
  if queue['entry']['state']=='waiting':post(doctor,'/api/v1/appointments/queue-entries/'+queue['entry']['id']+'/start',{},et,label+'-start')
  return appointment
 def clinical(label,rx):
  a=checkin(label);aid=a['id'];content={'summary':'Fictional Phase10 consultation','assessment':'Educational synthetic fixture','plan':'Synthetic follow-up booking'}
  c=create(label+'_consult',doctor,'/api/v1/records/consultations',{'appointment_id':aid,'clinical_content':content})
  c,et,_=doctor.call('GET','/api/v1/records/consultations/'+c['id'])
  if c['status']=='draft':
   changed,et,_=doctor.call('PATCH','/api/v1/records/consultations/'+c['id'],{'clinical_content':{**content,'plan':'Updated fictional follow-up plan'}},et);assert changed['clinical_content']['plan'].startswith('Updated')
   create(label+'_final',doctor,'/api/v1/records/consultations/'+c['id']+'/finalize',{'prescription_items':[{'medicine_id':r['medicine']['id'],'quantity':2,'dosage':'Synthetic dose','instructions':'Educational fixture only'}]if rx else []},et,(200,))
  return a,r[label+'_consult'],r[label+'_final']
 for label,rx in (('clinical_rx',True),('clinical_no_rx',False)):
  if label+'_connected_journey'in checks:continue
  a,c,final=clinical(label,rx);record=final['record'];record_path='/api/v1/records/'+record['id'];original,et,_=doctor.call('GET',record_path)
  dispensings=[]
  if rx:
   prescription=final['prescription'];reserve=create(label+'_reserve',pharm,'/api/v1/pharmacy/reservations',{'prescription_id':prescription['id'],'items':[{'prescription_item_id':prescription['items'][0]['id'],'quantity':2}]})
   _,et,_=pharm.call('GET','/api/v1/pharmacy/reservations/'+reserve['id']);revalidated=create(label+'_revalidate',pharm,'/api/v1/pharmacy/reservations/'+reserve['id']+'/revalidate',{},et,(200,))
   _,et,_=pharm.call('GET','/api/v1/pharmacy/reservations/'+reserve['id']);dispense=create(label+'_dispense',pharm,'/api/v1/pharmacy/reservations/'+reserve['id']+'/dispense',{},et);dispensings=[dispense['id']]
  invoice=create(label+'_invoice',billing,'/api/v1/billing/invoices',{'appointment_id':a['id'],'currency':'INR'});path='/api/v1/billing/invoices/'+invoice['id'];_,et,_=billing.call('GET',path)
  charged=create(label+'_charges',billing,path+'/charges',{'consultation_id':c['id'],'dispensing_ids':dispensings},et,(200,));assert charged['total_minor']==(15000 if rx else 10000)
  _,et,_=billing.call('GET',path);again=create(label+'_charges_replay',billing,path+'/charges',{'consultation_id':c['id'],'dispensing_ids':dispensings},et,(200,));assert again['total_minor']==charged['total_minor']and len(again['items'])==len(charged['items'])
  _,et,_=p.call('GET',path);payment=create(label+'_payment',p,path+'/payments',{'amount_minor':charged['total_minor'],'currency':'INR','simulated_outcome':'success'},et);assert payment['status']=='success'
  paid,_,_=p.call('GET',path);assert paid['balance_minor']==0;other.call('GET',path,codes=(404,))
  jid=p.call('GET','/api/v1/appointments/'+a['id']+'/workflow')[0]['journey_id'];jpath='/api/v1/appointments/journeys/'+jid
  for _ in range(12):
   journey,et,_=reception.call('GET',jpath);reconciled,_,code=post(reception,jpath+'/reconcile',{},et,codes=(200,412))
   if code==200 and reconciled['discharge_eligible']:break
   time.sleep(1)
  assert reconciled['discharge_eligible'];post(reception,jpath+'/discharge',{'reason':'Synthetic Phase10 accepted owner stages'},f'"{reconciled["version"]}"',label+'-discharge');checked(label+'_connected_journey')
 for label in ('clinical_rx','clinical_no_rx'):
  final=r[label+'_final'];record=final['record'];record_path='/api/v1/records/'+record['id'];original,et,_=doctor.call('GET',record_path)
  # Authorship permits reading, but historical amendment still needs current
  # care scope or an explicit unexpired patient grant after finalization.
  grant=create(label+'_grant',p,'/api/v1/records/access-grants',{'patient_id':p.data['profile']['id'],'grantee_user_id':doctor.data['profile']['user_id'],'scope':'records:read','expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
  revised=create(label+'_amendment',doctor,record_path+'/amendments',{'content':{'summary':'Fictional Phase10 amended record','assessment':'Synthetic amendment verification','plan':'Updated follow-up'},'reason':'Synthetic immutable revision acceptance'},et)
  p.call('GET',record_path);other.call('GET',record_path,codes=(404,))
  history=p.call('GET','/api/v1/records/patients/'+p.data['profile']['id']+'?limit=100')[0];assert history['items']

  checked(label+'_immutable_amendment')
 (ROOT/'docs/phase-10/evidence/focused-http.json').write_text(json.dumps({'checks':checks,'isolated':True,'raw_tokens_recorded':False},indent=2)+'\n')
if __name__=='__main__':main()
