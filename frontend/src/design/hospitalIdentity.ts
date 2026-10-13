import { useSyncExternalStore } from "react";
// Owner-confirmed display identity only; never tokens or persistent browser storage.
let identity: { subject: string; name: string } | null = null;
const listeners = new Set<() => void>();
export function publishHospitalIdentity(subject: string, name: string) {
  if (identity?.subject === subject && identity.name === name) return;
  identity = { subject, name };
  listeners.forEach((fn) => fn());
}
export function clearHospitalIdentity() {
  identity = null;
  listeners.forEach((fn) => fn());
}
export function useHospitalIdentity(subject?: string) {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    () => (identity && identity.subject === subject ? identity.name : null),
    () => null,
  );
}
