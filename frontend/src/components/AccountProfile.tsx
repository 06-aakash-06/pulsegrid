import { Resource } from "../hospital/ui";
import { ProfileEditor } from "../hospital/patientDoctor";
import type { PatientProfile } from "../api/authApi";
/** Loaded on demand from the account menu on every patient route. */
export function AccountProfile() {
 return <Resource<PatientProfile> path="/api/v1/patients/me" showReload={false}>{(profile,etag,refresh)=><ProfileEditor key={profile.version} profile={profile} etag={etag} path="/api/v1/patients/me" refresh={refresh}/>}</Resource>;
}
