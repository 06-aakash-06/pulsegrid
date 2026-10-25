import { PageHeaderSlot, PageRefreshControl } from "./PageTools";
import type { ReactNode } from "react";
import { DepartmentIcon, type Department } from "../design/DepartmentIcon";

/** Shared solid heading surface for every hospital workspace. */
export function PageHeader({ title, subtitle, department, actions, id }: {
  title: string; subtitle: string; department: Department; actions?: ReactNode; id?: string;
}) {
  return <header className={`page-header page-header--${department}`}>
    <span className="page-header__icon" aria-hidden="true"><DepartmentIcon department={department} /></span>
    <div className="page-header__copy"><h1 id={id}>{title}</h1><p title={subtitle}>{subtitle}</p></div>
    <div className="page-header__actions">{actions}<PageHeaderSlot /><PageRefreshControl /></div>
  </header>;
}
