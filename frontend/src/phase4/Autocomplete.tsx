import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import type { ApiClient } from "../api/client";
import { feedbackMessage } from "./api";
import type {
  DoctorAutocompleteProps,
  MedicineAutocompleteProps,
  Suggestion,
  SuggestionKind,
  SuggestionPage,
} from "./contracts";

interface AutocompleteBaseProps {
  api: ApiClient;
  kind: "doctor" | "specialty" | "medicine";
  label: string;
  placeholder: string;
  id?: string;
  disabled?: boolean;
  onSelect(suggestion: Suggestion): void;
}

function isAbort(error: unknown): boolean {
  return typeof error === "object" && error !== null && "name" in error && error.name === "AbortError";
}

function suggestionPage(value: unknown): value is SuggestionPage {
  if (typeof value !== "object" || value === null) return false;
  const page = value as Partial<SuggestionPage>;
  return Array.isArray(page.items)
    && (page.source === "trie" || page.source === "database")
    && (page.index_version === null || (Number.isSafeInteger(page.index_version) && (page.index_version as number) > 0))
    && page.items.every((item) => typeof item === "object" && item !== null
      && typeof item.id === "string"
      && typeof item.label === "string"
      && ["doctor", "specialty", "medicine"].includes(item.kind));
}

function Autocomplete({
  api,
  kind,
  label,
  placeholder,
  id,
  disabled = false,
  onSelect,
}: AutocompleteBaseProps) {
  const generatedId = useId().replaceAll(":", "");
  const inputId = id ?? "phase4-autocomplete-" + generatedId;
  const listId = inputId + "-options";
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Suggestion[]>([]);
  const [source, setSource] = useState<SuggestionPage["source"] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [focused, setFocused] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [selected, setSelected] = useState(false);
  const requestVersion = useRef(0);

  useEffect(() => {
    const prefix = query.trim();
    const version = ++requestVersion.current;
    if (selected) {
      setLoading(false);
      setError(null);
      setItems([]);
      setSource(null);
      setActiveIndex(-1);
      return;
    }
    if (!prefix) {
      setLoading(false);
      setError(null);
      setItems([]);
      setSource(null);
      setActiveIndex(-1);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setItems([]);
    setSource(null);
    setActiveIndex(-1);

    const timeout = window.setTimeout(() => {
      const params = new URLSearchParams({
        prefix,
        limit: "10",
      });
      let path: string;
      if (kind === "medicine") {
        path = "/api/v1/pharmacy/medicines/autocomplete?" + params.toString();
      } else {
        params.set("kinds", kind);
        path = "/api/v1/doctors/autocomplete?" + params.toString();
      }

      void api.requestWithMetadata<unknown>(path, {
        method: "GET",
        signal: controller.signal,
        referrerPolicy: "no-referrer",
      }).then((response) => {
        if (controller.signal.aborted || version !== requestVersion.current) return;
        if (!suggestionPage(response.data)) {
          throw new Error("The autocomplete service returned an unsupported response.");
        }
        const matching = response.data.items.filter((item) => item.kind === kind);
        setItems(matching);
        setSource(response.data.source);
        setError(null);
      }).catch((requestError: unknown) => {
        if (controller.signal.aborted || version !== requestVersion.current || isAbort(requestError)) return;
        setItems([]);
        setSource(null);
        setError(requestError);
      }).finally(() => {
        if (!controller.signal.aborted && version === requestVersion.current) setLoading(false);
      });
    }, 150);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [api, kind, query, retryCount, selected]);

  const listVisible = focused && Boolean(query.trim())
    && (loading || error !== null || items.length > 0 || (!loading && !error));

  function updateQuery(value: string) {
    requestVersion.current += 1;
    setFocused(true);
    setSelected(false);
    setQuery(value);
    setItems([]);
    setSource(null);
    setError(null);
    setActiveIndex(-1);
    setLoading(Boolean(value.trim()));
  }

  function choose(item: Suggestion) {
    requestVersion.current += 1;
    setSelected(true);
    setQuery(item.label);
    setItems([]);
    setSource(null);
    setError(null);
    setActiveIndex(-1);
    setFocused(false);
    onSelect(item);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (items.length > 0) setActiveIndex((index) => Math.min(index + 1, items.length - 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (items.length > 0) setActiveIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === "Enter" && activeIndex >= 0 && items[activeIndex]) {
      event.preventDefault();
      choose(items[activeIndex]);
      return;
    }
    if (event.key === "Escape") {
      setFocused(false);
      setActiveIndex(-1);
    }
  }

  const kindLabel = kind === "doctor" ? "Doctor" : kind === "specialty" ? "Specialty" : "Medicine";

  return (
    <div className="phase4-autocomplete">
      <label htmlFor={inputId}>{label}</label>
      <div className="phase4-autocomplete__input-wrap">
        <input
          id={inputId}
          type="search"
          role="combobox"
          aria-autocomplete="list"
          aria-controls={listId}
          aria-expanded={listVisible}
          aria-activedescendant={activeIndex >= 0 && items[activeIndex]
            ? listId + "-option-" + activeIndex
            : undefined}
          autoComplete="off"
          placeholder={placeholder}
          value={query}
          disabled={disabled}
          onChange={(event) => updateQuery(event.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
        />
        {loading && <span className="phase4-autocomplete__spinner" aria-hidden="true" />}
      </div>

      {listVisible && (
        <div className="phase4-autocomplete__popup">
          <ul className="phase4-autocomplete__list" id={listId} role="listbox" aria-label={kindLabel + " suggestions"}>
            {items.map((item, index) => (
              <li
                className={index === activeIndex ? "phase4-autocomplete__option is-active" : "phase4-autocomplete__option"}
                id={listId + "-option-" + index}
                key={item.kind + ":" + item.id}
                role="option"
                aria-selected={index === activeIndex}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(item)}
              >
                <span>{item.label}</span>
                <span className="phase4-autocomplete__kind">{item.kind}</span>
              </li>
            ))}
          </ul>
          {loading && <p className="phase4-inline-status" role="status">Searching {kindLabel.toLowerCase()} suggestions…</p>}
          {!loading && !error && items.length === 0 && <p className="phase4-inline-status" role="status">No {kindLabel.toLowerCase()} suggestions found.</p>}
          {error !== null && (
            <div className="phase4-autocomplete__error" role="status" aria-live="polite">
              <p>{feedbackMessage(error, kindLabel + " search")}</p>
              <button
                type="button"
                className="phase4-text-button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => setRetryCount((count) => count + 1)}
              >
                Retry search
              </button>
            </div>
          )}
          {!loading && !error && source && (
            <p className="phase4-feature-indicator" role="status">
              {source === "trie" ? "Indexed suggestions" : "Current database search"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function DoctorAutocomplete({
  api,
  kind = "doctor",
  label,
  placeholder,
  id,
  disabled,
  onSelect,
}: DoctorAutocompleteProps) {
  return (
    <Autocomplete
      api={api}
      kind={kind as SuggestionKind}
      label={label ?? (kind === "specialty" ? "Specialty" : "Doctor")}
      placeholder={placeholder ?? (kind === "specialty" ? "Search specialties" : "Search doctors")}
      id={id}
      disabled={disabled}
      onSelect={onSelect}
    />
  );
}

export function MedicineAutocomplete({
  api,
  label = "Medicine",
  placeholder = "Search medicines",
  id,
  disabled,
  onSelect,
}: MedicineAutocompleteProps) {
  return (
    <Autocomplete
      api={api}
      kind="medicine"
      label={label}
      placeholder={placeholder}
      id={id}
      disabled={disabled}
      onSelect={onSelect}
    />
  );
}
