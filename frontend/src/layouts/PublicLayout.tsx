import { Outlet } from "react-router-dom";
import { HospitalHeader } from "../design/HospitalHeader";
export function PublicLayout() { return <div className="public-page environment-reception"><HospitalHeader/><Outlet/><footer className="public-footer-note"><span>PulseGrid</span><p>General Hospital · Care, connected.</p></footer></div>; }
