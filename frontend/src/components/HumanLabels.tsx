import { useResource } from "../hospital/ui";
/** Name lookup stays subject to the existing patient API's authorization. */
export function QueuePatientName({patientId,name}:{patientId:string;name?:string}) {
 const patient=useResource<{display_name:string}>(name ? null : `/api/v1/patients/${patientId}`);
 return <span>{name ?? patient.response?.data.display_name ?? (patient.loading ? "Loading patient…" : "Name unavailable")}</span>;
}

export function PrescriptionDate({consultationId}:{consultationId:string}) {
 const consultation=useResource<{appointment_id:string}>(`/api/v1/records/consultations/${consultationId}`);
 const appointment=useResource<{starts_at:string}>(consultation.response?`/api/v1/appointments/${consultation.response.data.appointment_id}`:null);
 return appointment.response ? <time dateTime={appointment.response.data.starts_at}>{new Date(appointment.response.data.starts_at).toLocaleDateString('en-GB',{day:'numeric',month:'short',timeZone:'UTC'})}</time> : <span>{appointment.loading||consultation.loading?"Loading…":"Date unavailable"}</span>;
}
export function PrescriptionDoctor({consultationId}:{consultationId:string}) {
 const consultation=useResource<{doctor_id:string}>(`/api/v1/records/consultations/${consultationId}`);
 const doctor=useResource<{display_name:string}>(consultation.response?`/api/v1/doctors/${consultation.response.data.doctor_id}`:null);
 return <span>{doctor.response?.data.display_name??(doctor.loading||consultation.loading?"Loading…":"Doctor unavailable")}</span>;
}
function MedicineName({id}:{id:string}){const medicine=useResource<{name:string}>(`/api/v1/pharmacy/medicines/${id}`);return <span>{medicine.response?.data.name??"Medicine"}</span>;}
export function MedicineNames({items}:{items:{medicine_id:string}[]}) {return <>{items.map((item,i)=><span key={`${item.medicine_id}-${i}`}>{i>0?", ":""}<MedicineName id={item.medicine_id}/></span>)}</>;}
export function VisitLabel({appointmentId}:{appointmentId:string}) {
 const appointment=useResource<{starts_at:string;doctor_id:string}>(`/api/v1/appointments/${appointmentId}`);
 const doctor=useResource<{display_name:string}>(appointment.response?`/api/v1/doctors/${appointment.response.data.doctor_id}`:null);
 return <span>{appointment.response?<><time dateTime={appointment.response.data.starts_at}>{new Date(appointment.response.data.starts_at).toLocaleDateString('en-GB',{day:'numeric',month:'short',timeZone:'UTC'})}</time>{doctor.response?` · ${doctor.response.data.display_name}`:" · Consultation"}</>:"Consultation"}</span>;
}
