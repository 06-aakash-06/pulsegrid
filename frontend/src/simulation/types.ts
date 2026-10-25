import type { Role } from "../auth/authContext";

/** How a step decides it is finished. `manual` steps show a Next button (also Enter). */
export type AdvanceOn =
  | { type: "click" }
  | { type: "route"; value: string }
  | { type: "visible"; value: string }
  | { type: "event"; value: string }
  | { type: "manual" };

export interface TourApi {
  navigate: (path: string) => void;
  /** Opens a closed `<details>` that contains, or is, the element with this `data-tour` id. */
  openDisclosure: (tourId: string) => void;
}

export interface TourStep {
  id: string;
  /** Path the step lives on; the guide navigates there first when the user is elsewhere. */
  route?: string;
  /** `data-tour` id of the element to highlight. */
  target: string;
  /** Further `data-tour` ids that stay clickable, such as a dropdown that opens beside the target. */
  extraTargets?: string[];
  title: string;
  body: string;
  behindTheScenes?: string;
  advanceOn: AdvanceOn;
  prepare?: (api: TourApi) => void;
  /** Steps that change server state. Skipped on a live backend unless demo actions are allowed. */
  mutates?: boolean;
  /** Suggested text the user can type; the end-to-end check types it for them. */
  suggestion?: string;
  /** `<select>` value the end-to-end check picks. */
  choose?: string;
}

export interface Tour {
  id: string;
  /** Role whose workspace the tour runs in; `null` for tours that need no particular role. */
  role: Role | null;
  /** Workspace base path, such as `/patient`. */
  workspace: string | null;
  roleLabel: string;
  title: string;
  goal: string;
  summary: string;
  steps: TourStep[];
}

export type SimulationStatus = "idle" | "picking" | "running" | "done";

/** How the walkthrough reaches the tour's workspace: already there, signing in, or signing out first. */
export type TourEntry = "direct" | "sign-in" | "switch";

export interface SimulationState {
  status: SimulationStatus;
  tourId: string | null;
  index: number;
  allowActions: boolean;
  entry: TourEntry;
  /** Increments on every start and restart so a replayed step prepares again. */
  run: number;
}
