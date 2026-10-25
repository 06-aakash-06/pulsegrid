import { PageRefresh } from "../components/PageTools";
import { Link } from "react-router-dom";
import { useResource } from "./ui";
import type { Page, UserView, Doctor } from "./models";

export function AdminHome() {
  const users=useResource<Page<UserView>>("/api/v1/patients/users?limit=20");
  const doctors=useResource<Page<Doctor>>("/api/v1/doctors?limit=20");
  const links=[
    {path:"staff",title:"Staff & roles",description:"Manage accounts, access and staff roles.",data:users.response?.data},
    {path:"doctors",title:"Consultation",description:"Manage doctor profiles and schedule changes.",data:doctors.response?.data},
    {path:"control-room",title:"Control Room",description:"Check service health and operational alerts."},
    {path:"traces",title:"Trace Explorer",description:"Investigate recent service requests."},
    {path:"settings",title:"Administration desk",description:"Find hospital administration tools."},
  ];
  return <><PageRefresh onClick={()=>{users.refresh();doctors.refresh();}} disabled={users.loading||doctors.loading}>Refresh</PageRefresh><div className="admin-home">{links.map(link=><Link key={link.path} to={`/admin/${link.path}`} className="task-link"><h2>{link.title}</h2><p>{link.description}</p>{link.data&&<span>{link.data.items.length}{link.data.next_cursor?"+":""} {link.path==='staff'?"accounts":"doctors"}{link.data.next_cursor?" shown":""}</span>}<strong>Open →</strong></Link>)}</div>{users.error&&<p role="alert">{users.error}</p>}{doctors.error&&<p role="alert">{doctors.error}</p>}</>;
}
