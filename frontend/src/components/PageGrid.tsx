import type { ReactNode } from "react";
export function PageGrid({ children, preset = "main", className = "" }: {
  children: ReactNode; preset?: "main" | "main+aside" | "three"; className?: string;
}) {
  return <div className={`page-grid page-grid--${preset.replace('+', '-')} ${className}`}>{children}</div>;
}
