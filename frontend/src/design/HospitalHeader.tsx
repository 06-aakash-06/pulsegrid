import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Brand } from '../components/Brand';
import { useAuth } from '../auth/authContext';
import { workspaces } from '../navigation/workspaces';
import { DepartmentIcon, departmentFor } from './DepartmentIcon';
export function HospitalHeader({ roleLabel, onMenu, menuOpen = false, onLogout }: { roleLabel?: string; onMenu?: () => void; menuOpen?: boolean; onLogout?: () => void }) {
 const { state } = useAuth();
 const [search,setSearch] = useState('');
 const [notice,setNotice] = useState(false);
 const dialog = useRef<HTMLDialogElement>(null);
 const location = useLocation();
 const allowed = state.status === 'authenticated' ? workspaces.filter(w=>w.roles.some(r=>state.roleHints.includes(r))) : [];
 const destinations = allowed.flatMap(w=>w.pages.map(p=>({to:`${w.basePath}/${p.path}`,label:p.title,role:w.roleLabel,department:departmentFor(w.basePath,p.path)})));
 useEffect(()=>{dialog.current?.close?.();setNotice(false);},[location.pathname]);
 useEffect(()=>{ const handler=(e:KeyboardEvent)=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();dialog.current?.showModal();}};document.addEventListener('keydown',handler);return()=>document.removeEventListener('keydown',handler); },[]);
 const identity = state.status === 'authenticated' ? `Account ${state.user.id ?? 'signed in'}` : 'Welcome';
 return <header className="hospital-header">
  {onMenu && <button className="menu-toggle" aria-label={menuOpen?'Close navigation menu':'Open navigation menu'} aria-expanded={menuOpen} aria-controls="workspace-navigation" onClick={onMenu} type="button"><span/><span/><span/></button>}
  <Brand/><p className="hospital-tagline">A Smarter Hospital. A Healthier Tomorrow.</p>
  <button className="global-search" onClick={()=>dialog.current?.showModal()} type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6"/></svg><span>Search hospital departments & workflows…</span><kbd>⌘ K</kbd></button>
  <div className="header-account">
   <div className="notification-wrap"><button className="notification-button" aria-label="Notifications" aria-expanded={notice} onClick={()=>setNotice(!notice)} type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5ZM10 21h4M12 2v2"/></svg></button>{notice && <div className="header-popover" role="status"><strong>Hospital updates</strong><p>A notification feed is not available. Check your appointment, queue or journey for owner-confirmed updates.</p></div>}</div>
   {state.status === 'authenticated' ? <details className="account-menu"><summary><span className="account-avatar" aria-hidden="true"><DepartmentIcon department="reception"/></span><span><strong>{identity}</strong><small>{roleLabel ?? 'Signed in'}</small></span><span aria-hidden="true">⌄</span></summary><div className="header-popover"><p>Signed in as {roleLabel ?? 'hospital user'}</p>{allowed.map(w=><Link key={w.basePath} to={`${w.basePath}/dashboard`}>{w.name} →</Link>)}{onLogout && <button type="button" onClick={onLogout}>Sign out</button>}</div></details> : <nav aria-label="Main navigation"><Link to="/login">Sign in</Link><Link className="button button--small" to="/register">Create patient account</Link></nav>}
  </div>
  <dialog ref={dialog} className="command-search" aria-labelledby="search-heading"><div className="command-heading"><h2 id="search-heading">Find your way</h2><button aria-label="Close hospital search" type="button" onClick={()=>dialog.current?.close?.()}>✕</button></div><label>Search your available workflows<input autoFocus value={search} onChange={e=>setSearch(e.target.value)} placeholder="Appointments, medicines, records…"/></label><p>Search within a department using its existing search tools.</p><nav aria-label="Search results">{destinations.filter(d=>`${d.label} ${d.role}`.toLowerCase().includes(search.toLowerCase())).map(d=><Link key={d.to} to={d.to}><DepartmentIcon department={d.department}/><span>{d.label}<small>{d.role}</small></span><span>→</span></Link>)}{!destinations.length && <Link to="/login">Sign in to search your permitted hospital workflows →</Link>}</nav><button type="button" onClick={()=>dialog.current?.close?.()}>Close</button></dialog>
 </header>;
}
