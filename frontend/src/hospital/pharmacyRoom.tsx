import { useEffect, useId, useState, type ReactNode } from "react";
import { useAuth } from "../auth/authContext";
import { MedicineAutocomplete } from "../phase4";
import type { Medicine, Page } from "./models";
import { Inputs, query, useResource, type Values } from "./ui";

export const availabilityText: Record<Medicine["availability"], string> = {
  available: "Available",
  unavailable: "Unavailable",
  unknown: "Availability not supplied",
};

export function medicineLabel(item: Pick<Medicine, "id" | "name">) {
  return item.name.startsWith("Synthetic") ? `Catalog medicine …${item.id.slice(-4)}` : item.name;
}

const cartonTones = ["teal", "red", "ochre", "blue"] as const;
const BAYS = "ABCDEFG".split("");

/** Bounded cursor paging for one owner collection; resets when its path changes. */
export function useCursorPage<T>(path: string | null, revision = 0) {
  const [nav, setNav] = useState<{ path: string | null; cursor?: string; history: (string | undefined)[] }>({ path, history: [] });
  const current = nav.path === path ? nav : { path, cursor: undefined, history: [] };
  const paged = path
    ? `${path}${path.includes("?") ? "&" : "?"}limit=20${current.cursor ? `&cursor=${encodeURIComponent(current.cursor)}` : ""}`
    : null;
  const resource = useResource<Page<T>>(paged, revision);
  const data = resource.response?.data;
  return {
    items: data?.items ?? [],
    loaded: !!data,
    loading: resource.loading,
    error: resource.error,
    refresh: resource.refresh,
    pageNumber: current.history.length + 1,
    hasPrevious: current.history.length > 0,
    hasNext: !!data?.next_cursor,
    previous: () => setNav({ path, cursor: current.history.at(-1), history: current.history.slice(0, -1) }),
    next: () => data?.next_cursor && setNav({ path, cursor: data.next_cursor, history: [...current.history, current.cursor] }),
  };
}

export function PharmacyRoom({
  cabinet,
  stand,
  tray,
  right,
}: {
  title: string;
  workspaceName: string;
  cabinet: ReactNode;
  stand: ReactNode;
  tray: ReactNode;
  right: ReactNode;
}) {

  return (
    <div className="pharmacy-room">
      <div className="pharmacy-room__cabinet">{cabinet}</div>
      <div className="pharmacy-room__counter">
        {stand}
        <div className="counter-tray">{tray}</div>
      </div>
      <div className="pharmacy-room__right"><div className="pharmacy-room__right-stack">{right}</div></div>
      <div className="pharmacy-counter-front" aria-hidden="true" />
    </div>
  );
}

export function MedicineCabinet({
  staff = false,
  selected,
  onSelect,
  revision = 0,
  showSelection = false,
}: {
  staff?: boolean;
  selected: string | null;
  onSelect: (id: string | null) => void;
  revision?: number;
  showSelection?: boolean;
}) {
  const { state, api } = useAuth();
  const titleId = useId();
  const [draft, setDraft] = useState<Values>({});
  const [filters, setFilters] = useState<Values>({});
  const [searchError, setSearchError] = useState("");
  const [availability, setAvailability] = useState<Medicine["availability"] | "">("");
  const shelf = useCursorPage<Medicine>(query("/api/v1/pharmacy/medicines", filters), revision);
  const visible = shelf.items.filter(
    (item) => !availability || item.availability === availability,
  );
  const firstVisible = visible[0]?.id;
  useEffect(() => {
    if (!selected && firstVisible) onSelect(firstVisible);
  }, [selected, firstVisible, onSelect]);
  const selection = useResource<Medicine>(showSelection && selected ? `/api/v1/pharmacy/medicines/${selected}` : null, revision);
  const filterLabel = availability ? availabilityText[availability] : "";

  return (
    <section className="medicine-cabinet" aria-labelledby={titleId}>
      <div className="cabinet-rail">
        <h2 id={titleId} className="sr-only">Medicine cabinet</h2>
        <div className="cabinet-rail__row">
          <div className="cabinet-rail__search">
            <MedicineAutocomplete
              api={api}
              roleHints={state.status === "authenticated" ? state.roleHints : []}
              label="Find a medicine"
              placeholder="Search medicines…"
              onSelect={(item) => onSelect(item.id)}
            />
          </div>
          <div className="cabinet-rail__pages" role="group" aria-label="Shelf pages">
            <button type="button" disabled={!shelf.hasPrevious || shelf.loading} onClick={shelf.previous} aria-label="Previous shelf page">‹ Prev</button>
            <span>Page {shelf.pageNumber}</span>
            <button type="button" disabled={!shelf.hasNext || shelf.loading} onClick={shelf.next} aria-label="Next shelf page">Next ›</button>
            <button type="button" disabled={shelf.loading} onClick={shelf.refresh}>Refresh</button>
          </div>
        </div>
        <div className="cabinet-rail__row">
          <div className="cabinet-rail__filters" role="group" aria-label="Availability on this shelf page">
            {([["", "All"], ["available", "Available"], ["unavailable", "Unavailable"], ["unknown", "Availability not supplied"]] as const).map(([value, label]) => (
              <button
                type="button"
                key={value}
                aria-pressed={availability === value}
                onClick={() => {
                  setAvailability(value);
                  onSelect(null);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <details className="cabinet-rail__options">
            <summary>More search options</summary>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (draft.q && (draft.q.trim().length < 2 || draft.q.trim().length > 100)) {
                  setSearchError("Search must contain 2 to 100 characters.");
                  return;
                }
                setFilters(draft);
                onSelect(null);
                setSearchError("");
              }}
            >
              <Inputs
                fields={[
                  { name: "q", label: "Medicine search", max: 100 },
                  ...(staff ? [{ name: "active", label: "Medicine active filter", kind: "select" as const, options: ["true", "false"] }] : []),
                ]}
                values={draft}
                change={(name, value) => setDraft({ ...draft, [name]: value })}
              />
              <button>Search medicines</button>
              {searchError && <p role="alert">{searchError}</p>}
            </form>
          </details>
        </div>
      </div>
      <div className="shelf-face">
        <ol className="shelf-bays" aria-hidden="true">{BAYS.map((bay) => <li key={bay}>Bay {bay}</li>)}</ol>
        {shelf.loading && <p role="status" className="shelf-message">Loading medicines…</p>}
        {shelf.error && <p role="alert" className="shelf-message">{shelf.error}</p>}
        {shelf.loaded && !shelf.loading && visible.length === 0 && (
          <p className="shelf-message">
            {filterLabel ? `No “${filterLabel}” medicines on shelf page ${shelf.pageNumber}. Other pages may hold more.` : "No medicines are on this shelf page."}
          </p>
        )}
        <ul className="shelf-grid" aria-label={`Medicines on shelf page ${shelf.pageNumber}`}>
          {visible.map((item, index) => {
            const label = medicineLabel(item);
            return (
              <li key={item.id} className="shelf-slot" data-selected={selected === item.id} data-availability={item.availability}>
                <span className="carton" aria-hidden="true" data-tone={cartonTones[(Number(item.id.slice(-2)) || index) % cartonTones.length]}>
                  <span>{label.split(/\s+/)[0]}</span>
                </span>
                <button type="button" className="shelf-label" aria-pressed={selected === item.id} title={label} onClick={() => onSelect(item.id)}>
                  <strong>{label}</strong>
                  <span>
                    {item.availability === "unknown" ? <><span className="sr-only">Availability </span>Not supplied</> : availabilityText[item.availability]}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      {showSelection && (
        <p className="cabinet-selection" aria-live="polite">
          {selection.response ? (
            <>
              <strong>{medicineLabel(selection.response.data)}</strong>
              <span>{availabilityText[selection.response.data.availability]} · advisory; Pharmacy confirms stock when a reservation is requested.</span>
            </>
          ) : selection.error ? (
            <span>{selection.error}</span>
          ) : (
            <span>Choose a medicine on the shelf to see its availability.</span>
          )}
        </p>
      )}
    </section>
  );
}
