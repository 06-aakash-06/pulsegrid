import type { SimulationState, Tour, TourEntry, TourStep } from "./types";

export const STORAGE_KEY = "pulsegrid.simulation";
export const COMMAND_SUCCESS_EVENT = "pulsegrid:command-success";

export const idleState: SimulationState = { status: "idle", tourId: null, index: 0, allowActions: false, entry: "direct", run: 0 };

export type SimulationAction =
  | { type: "pick" }
  | { type: "start"; tourId: string; allowActions: boolean; entry: TourEntry }
  | { type: "next"; count: number }
  | { type: "back" }
  | { type: "exit" }
  | { type: "restart" };

export function reduce(state: SimulationState, action: SimulationAction): SimulationState {
  switch (action.type) {
    case "pick":
      return { ...state, status: "picking" };
    case "start":
      return { status: "running", tourId: action.tourId, index: 0, allowActions: action.allowActions, entry: action.entry, run: state.run + 1 };
    case "next":
      if (state.status !== "running") return state;
      return state.index + 1 >= action.count ? { ...state, status: "done" } : { ...state, index: state.index + 1 };
    case "back":
      return state.status === "running" ? { ...state, index: Math.max(0, state.index - 1) } : state;
    case "restart":
      return state.tourId ? { ...state, status: "running", index: 0, run: state.run + 1 } : state;
    case "exit":
      return { ...idleState, run: state.run };
  }
}

/** Steps that bring a visitor to the tour's workspace by signing in with its quick sign-in account. */
export function entrySteps(tour: Tour, entry: TourEntry): TourStep[] {
  if (entry === "direct" || !tour.workspace) return [];
  const account = tour.workspace.slice(1);
  const steps: TourStep[] = [
    {
      id: "entry-quick-sign-in", route: "/login", target: `quick-sign-in-${account}`,
      title: `Choose ${tour.roleLabel}`,
      body: `Quick sign-in fills in the ${tour.roleLabel.toLowerCase()} account's email and password.`,
      advanceOn: { type: "click" },
    },
    {
      id: "entry-sign-in", target: "sign-in-submit", title: "Sign in",
      body: `Sign in to open the ${tour.roleLabel.toLowerCase()} workspace.`,
      behindTheScenes: "The Patient service checks the password, then issues a short-lived access token and a refresh cookie that only the server can read.",
      advanceOn: { type: "route", value: `^${tour.workspace}/` },
    },
  ];
  return entry === "switch"
    ? [{ id: "entry-sign-out", target: "sign-out", title: "Sign out first", body: `This walkthrough runs as ${tour.roleLabel.toLowerCase()}. Sign out of this account so you can sign in as one.`, advanceOn: { type: "route", value: "^/login" } }, ...steps]
    : steps;
}

/** Steps that may run here: every step against the sample hospital, read-only ones on a live server. */
export function runnableSteps(tour: Tour, sampleBackend: boolean, allowActions: boolean, entry: TourEntry = "direct"): TourStep[] {
  const own = sampleBackend || allowActions ? tour.steps : tour.steps.filter((step) => !step.mutates);
  return [...entrySteps(tour, entry), ...own];
}

export function routeMatches(pattern: string, pathname: string, search = ""): boolean {
  return new RegExp(pattern).test(`${pathname}${search}`);
}

export function readPersisted(): SimulationState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return idleState;
    const saved = JSON.parse(raw) as Partial<SimulationState>;
    if (saved.status !== "running" && saved.status !== "done") return idleState;
    if (typeof saved.tourId !== "string" || !Number.isInteger(saved.index)) return idleState;
    const entry = saved.entry === "sign-in" || saved.entry === "switch" ? saved.entry : "direct";
    return { status: saved.status, tourId: saved.tourId, index: saved.index!, allowActions: saved.allowActions === true, entry, run: Number.isInteger(saved.run) ? saved.run! : 1 };
  } catch {
    return idleState;
  }
}

export function persist(state: SimulationState) {
  try {
    if (state.status === "running" || state.status === "done") sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Without session storage a reload simply ends the walkthrough.
  }
}

export function announceCommandSuccess(command: string) {
  window.dispatchEvent(new CustomEvent(COMMAND_SUCCESS_EVENT, { detail: { command } }));
}

export function tourSelector(id: string) {
  return `[data-tour="${id.replace(/["\\]/g, "\\$&")}"]`;
}

// jsdom has no layout, so every element measures zero there.
const layoutless = typeof navigator !== "undefined" && /jsdom/i.test(navigator.userAgent);

/** First rendered element for a `data-tour` id; hidden duplicates (closed tabs, drawers) are ignored. */
export function findTarget(id: string): HTMLElement | null {
  const all = [...document.querySelectorAll<HTMLElement>(tourSelector(id))];
  return all.find((element) => {
    if (element.closest("details:not([open]) > :not(summary), [hidden], [inert]")) return false;
    if (layoutless) return true;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && getComputedStyle(element).visibility !== "hidden";
  }) ?? null;
}

export function findAny(id: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(tourSelector(id));
}
