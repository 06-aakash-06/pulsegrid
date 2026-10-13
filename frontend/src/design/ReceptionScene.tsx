import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { gsap } from 'gsap';
import { DepartmentIcon, type Department } from './DepartmentIcon';
const slips: {label:string;description:string;path:string;department:Department}[]=[
 {label:'Book an Appointment',description:'Find a doctor and schedule your visit',path:'doctors',department:'appointments'},
 {label:'My Appointments',description:'View and manage your upcoming visits',path:'appointments?view=upcoming',department:'appointments'},
 {label:'Check In',description:'Use your secure QR code or check-in link',path:'check-in',department:'waiting'},
 {label:'View Records',description:'Access your authorized medical history',path:'records',department:'records'},
];
export function ReceptionScene({name,publicView=false,children}:{name?:string;publicView?:boolean;children?:ReactNode}) {
 const scene=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(!window.matchMedia)return;const media=gsap.matchMedia();media.add('(prefers-reduced-motion: no-preference)',()=>{gsap.fromTo(scene.current?.querySelectorAll('.wayfinding-sign,.appointment-slip')??[],{y:10,opacity:.6},{y:0,opacity:1,duration:.45,stagger:.045,clearProps:'all'});});return()=>media.revert();},[]);
 const href=(path:string)=>`/patient/${path}`;
 return <div className={`reception-scene${publicView?' reception-scene--public':''}`} ref={scene}>
  <nav className="wayfinding" aria-label="Hospital wayfinding">{[{title:'Consultation',path:'doctors',sub:'Doctors & specialties',dep:'consultation'},{title:'Waiting Room',path:'queue',sub:'Your live queue',dep:'waiting'},{title:'Pharmacy',path:'pharmacy',sub:'Prescription fulfillment',dep:'pharmacy'},{title:'Emergency',path:'emergency',sub:'Urgent care requests',dep:'emergency'}].map(s=><Link key={s.path} className={`wayfinding-sign wayfinding-sign--${s.dep}`} to={href(s.path)}><DepartmentIcon department={s.dep as Department}/><span><strong>{s.title}</strong><small>{s.sub}</small></span><b aria-hidden="true">→</b></Link>)}</nav>
  <section className="welcome-wall"><div><p className="welcome-intro">{publicView?'Welcome to':'Welcome back,'}</p><h2>{publicView?'PulseGrid.':name ? `${name}.`:'Your hospital.'}</h2><p className="welcome-motto">CARE · COORDINATION · CLARITY</p></div><aside className="reception-guidance"><p className="eyebrow">YOUR VISIT, CONNECTED</p><p>Find your doctor.<br/>Plan your appointment.<br/>Follow your care journey.</p>{publicView&&<Link className="button" to="/login">Sign in to PulseGrid <span aria-hidden="true">→</span></Link>}</aside></section>
  <div className="robot-conversation"><p>Hello{ name ? ` ${name}`:''}.<br/>Find your way with the hospital directory.</p><span aria-hidden="true">✦</span></div>
  <div className="reception-counter"><p className="reception-counter-label">RECEPTION</p><div className="appointment-slips">{slips.map(s=><Link className="appointment-slip" key={s.label} to={href(s.path)}><DepartmentIcon department={s.department}/><strong>{s.label}</strong><p>{s.description}</p><span className="slip-arrow" aria-hidden="true">→</span></Link>)}</div></div>
  {children}
 </div>;
}
