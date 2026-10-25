import type { ReactNode } from "react";
import type { Department } from "./DepartmentIcon";
import { PageHeader } from "../components/PageHeader";

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
  return <PageHeader department={department} title={title} subtitle={subtitle} actions={children} />;
}
