import { useEffect, useState } from "react";
import { useResource } from "../hospital/ui";
import type { Doctor, Page } from "../hospital/models";
import { DoctorPortrait, useLocalDemo } from "./localDemo";

export function AppointmentDoctorRail({selected,onSelect}:{selected:string;onSelect:(doctor:Doctor)=>void}) {
  const demo=useLocalDemo();
  const [search,setSearch]=useState("");
  const [specialty,setSpecialty]=useState("");
  const [cursor,setCursor]=useState<string|undefined>();
  const [history,setHistory]=useState<(string|undefined)[]>([]);
  const roster=useResource<Page<Doctor>>(`/api/v1/doctors?limit=20${cursor?`&cursor=${encodeURIComponent(cursor)}`:''}`);
  const rows=roster.response?.data.items??[];
  useEffect(()=>{if(!selected&&rows[0])onSelect(rows[0]);},[selected,roster.response,demo,onSelect]);
  return <div className="appointment-doctor-rail">
    <label>Find a doctor<input type="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search doctors…" title="Search doctors by name or specialty"/></label>
    {roster.error&&<p role="alert">{roster.error}</p>}
    {roster.loading&&<p role="status">Loading doctors…</p>}
    <div className="appointment-specialties" aria-label="Doctor specialties"><button type="button" aria-pressed={!specialty} onClick={()=>setSpecialty("")}>All</button>{[...new Set(rows.flatMap(d=>d.specialties.map(s=>s.name)))].map(name=><button type="button" key={name} aria-pressed={specialty===name} onClick={()=>setSpecialty(name)}>{name}</button>)}</div>
    <div className="appointment-doctor-rows">{rows.filter(d=>(!specialty||d.specialties.some(s=>s.name===specialty))&&`${d.display_name} ${d.specialties.map(s=>s.name).join(' ')}`.toLowerCase().includes(search.toLowerCase())).map(d=><button type="button" key={d.id} aria-label={`Select ${d.display_name}, ${d.specialties.map(s=>s.name).join(", ")}`} aria-pressed={selected===d.id} onClick={()=>onSelect(d)}><DoctorPortrait name={d.display_name} index={demo?.doctors[d.id]?.portrait}/><span><strong>{d.display_name}</strong><small>{d.specialties.map(s=>s.name).join(', ')}</small></span><b aria-hidden="true">›</b></button>)}</div>
    {(roster.response?.data.next_cursor||history.length>0)&&<div className="doctor-rail-pagination"><button type="button" disabled={!history.length||roster.loading} onClick={()=>{setCursor(history.at(-1));setHistory(history.slice(0,-1));}}>Previous doctors</button><button type="button" disabled={!roster.response?.data.next_cursor||roster.loading} onClick={()=>{setHistory([...history,cursor]);setCursor(roster.response!.data.next_cursor!);}}>More doctors</button></div>}
  </div>;
}
