import { useEffect, useState } from "react";
export interface DemoHospital {
  label: string;
  doctors: Record<string, { portrait: number; label: string }>;
  patients: Record<string, { name: string; label: string }>;
  appointments: Record<string, { label: string }>;
  specialties: string[];
}
// Presentation metadata only. Production builds cannot enable this fetch.
export function useLocalDemo() {
  const [demo, setDemo] = useState<DemoHospital | null>(null);
  useEffect(() => {
    if (
      import.meta.env.MODE !== "development" ||
      import.meta.env.VITE_LOCAL_HOSPITAL_DEMO !== "true"
    )
      return;
    const abort = new AbortController();
    void fetch("/__demo/hospital.json", {
      signal: abort.signal,
      cache: "no-store",
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!abort.signal.aborted) setDemo(data);
      })
      .catch(() => {});
    return () => abort.abort();
  }, []);
  return demo;
}
export function DoctorPortrait({
  name,
  index,
  large = false,
}: {
  name: string;
  index?: number;
  large?: boolean;
}) {
  return index === undefined ? (
    <span
      className={`reference-portrait reference-portrait--initials${large ? " reference-portrait--large" : ""}`}
      aria-hidden="true"
    >
      {name
        .replace(/^Dr\.\s*/, "")
        .split(" ")
        .slice(0, 2)
        .map((n) => n[0])
        .join("")}
    </span>
  ) : (
    <span
      className={`reference-portrait${large ? " reference-portrait--large" : ""}`}
      role="img"
      aria-label={`Portrait of ${name}`}
      style={{
        backgroundImage: "url(/environments/demo-clinicians.webp)",
        backgroundPosition: `${(index % 3) * 50}% ${Math.floor(index / 3) * 100}%`,
      }}
    />
  );
}
