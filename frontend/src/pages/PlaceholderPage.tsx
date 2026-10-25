import { PageHeader } from "../components/PageHeader";
import { Link } from "react-router-dom";
import { DepartmentIcon } from "../design/DepartmentIcon";
import type { WorkspacePage } from "../navigation/workspaces";
export function PlaceholderPage({page}:{page:WorkspacePage;workspaceName:string}) {
 return <div className="page-stack department-page department-page--reception"><PageHeader department="reception" title={page.title} subtitle="Hospital administration and access" /><section className="administration-directory"><h2>Administration desk</h2><p>Manage the hospital through its existing owner interfaces.</p><Link to="/admin/staff"><DepartmentIcon department="reception"/><span><strong>Staff & account access</strong><small>Review identities, roles and account status.</small></span><span>→</span></Link><Link to="/admin/doctors"><DepartmentIcon department="consultation"/><span><strong>Doctor directory & schedules</strong><small>Maintain profiles and accepted schedule proposals.</small></span><span>→</span></Link><Link to="/admin/control-room"><DepartmentIcon department="control"/><span><strong>System operations</strong><small>Service health, infrastructure metrics and Surge Mode.</small></span><span>→</span></Link><p className="configuration-note">A separate hospital-settings API is not available. No configuration changes are submitted from this page.</p></section></div>;
}
