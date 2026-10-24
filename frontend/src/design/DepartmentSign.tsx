import type { ReactNode } from "react";
import { DepartmentIcon, type Department } from "./DepartmentIcon";

export function DepartmentSign({
  department,
  title,
  subtitle,
  children,
}: {
  department: Department;
  title: string;
  subtitle: string;
  children?: ReactNode;
}) {
  return (
    <header className={`department-sign department-sign--${department}`}>
      <span className="department-sign__mark" aria-hidden="true"><DepartmentIcon department={department} /></span>
      <div className="department-sign__name">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {children && <div className="department-sign__aside">{children}</div>}
    </header>
  );
}
