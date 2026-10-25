import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { COMMAND_SUCCESS_EVENT, findAny, findTarget, persist, readPersisted, reduce, routeMatches, runnableSteps, type SimulationAction } from "./engine";
import { GuideCard, SummaryCard } from "./GuideCard";
import { SimulationOverlay } from "./SimulationOverlay";
import { TourPicker } from "./TourPicker";
import { allTours } from "./tours/index";
import type { SimulationState, Tour, TourApi, TourEntry, TourStep } from "./types";
import { useTourTarget } from "./useTourTarget";

const defaultSampleBackend = import.meta.env.VITE_MOCK_API === "true" || import.meta.env.VITE_DEMO_MOCK === "true";

interface SimulationContextValue {
  state: SimulationState;
  tours: Tour[];
  sampleBackend: boolean;
  openPicker: () => void;
  start: (tour: Tour, allowActions: boolean) => void;
  exit: () => void;
}

const SimulationContext = createContext<SimulationContextValue | null>(null);
export const useSimulation = () => useContext(SimulationContext);

function useMedia(query: string) {
  const read = () => typeof window !== "undefined" && !!window.matchMedia?.(query).matches;
  const [matches, setMatches] = useState(read);
  useEffect(() => {
    const media = window.matchMedia?.(query);
    if (!media) return;
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, [query]);
  return matches;
}

export function SimulationProvider({ children, tours = allTours, sampleBackend = defaultSampleBackend }: { children: ReactNode; tours?: Tour[]; sampleBackend?: boolean }) {
  const [state, setState] = useState<SimulationState>(readPersisted);
  const dispatch = useCallback((action: SimulationAction) => setState((current) => reduce(current, action)), []);
  useEffect(() => persist(state), [state]);
  const { state: auth } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const mobile = useMedia("(max-width: 900px)");
  const reducedMotion = useMedia("(prefers-reduced-motion: reduce)");
  const tour = tours.find((item) => item.id === state.tourId) ?? null;
  const steps = useMemo<TourStep[]>(() => (tour ? runnableSteps(tour, sampleBackend, state.allowActions, state.entry) : []), [tour, sampleBackend, state.allowActions, state.entry]);
  const running = state.status === "running" && !!tour && steps.length > 0;
  const step = running ? steps[Math.min(state.index, steps.length - 1)] : null;
  const stepKey = `${state.tourId}:${state.run}:${state.index}`;
  const cardRef = useRef<HTMLDivElement>(null);
  const assisting = useRef(false);
  const assist = useCallback((run: () => void) => {
    assisting.current = true;
    try { run(); } finally { assisting.current = false; }
  }, []);
  const target = useTourTarget(step?.target ?? null, step?.extraTargets, { stepKey, mobile, reducedMotion, assist });

  const advancedFor = useRef<string | null>(null);
  const next = useCallback(() => {
    if (advancedFor.current === stepKey) return;
    advancedFor.current = stepKey;
    dispatch({ type: "next", count: steps.length });
  }, [dispatch, stepKey, steps.length]);
  useEffect(() => { advancedFor.current = null; }, [stepKey]);

  // Arrive on the step's page and run its preparation once per step.
  const prepared = useRef<string | null>(null);
  useEffect(() => {
    if (!step || prepared.current === stepKey) return;
    prepared.current = stepKey;
    if (step.route && !location.pathname.startsWith(step.route)) navigate(step.route);
    const api: TourApi = {
      navigate,
      openDisclosure: (id) => {
        const element = findAny(id);
        const details = element?.matches("details") ? (element as HTMLDetailsElement) : element?.closest("details");
        if (details && !details.open) assist(() => { details.open = true; });
      },
    };
    step.prepare?.(api);
  }, [step, stepKey, location.pathname, navigate, assist]);

  // Advance conditions.
  useEffect(() => {
    if (!step || step.advanceOn.type !== "route") return;
    if (routeMatches(step.advanceOn.value, location.pathname, location.search)) next();
  }, [step, location.pathname, location.search, next]);
  useEffect(() => {
    if (!step || step.advanceOn.type !== "visible") return;
    const id = step.advanceOn.value;
    const timer = window.setInterval(() => { if (findTarget(id)) next(); }, 250);
    return () => window.clearInterval(timer);
  }, [step, next]);
  useEffect(() => {
    if (!step || step.advanceOn.type !== "event") return;
    const command = step.advanceOn.value;
    const handler = (event: Event) => { if ((event as CustomEvent<{ command?: string }>).detail?.command === command) next(); };
    window.addEventListener(COMMAND_SUCCESS_EVENT, handler);
    return () => window.removeEventListener(COMMAND_SUCCESS_EVENT, handler);
  }, [step, next]);

  // While a step is active only the target, its companions and the guide card take clicks.
  useEffect(() => {
    if (!step) return;
    const allowed = (node: EventTarget | null) => {
      if (!(node instanceof Node)) return false;
      if (cardRef.current?.contains(node)) return true;
      return [step.target, ...(step.extraTargets ?? [])].some((id) => findTarget(id)?.contains(node));
    };
    const guard = (event: MouseEvent) => {
      if (assisting.current || allowed(event.target)) {
        if (event.type === "click" && step.advanceOn.type === "click" && findTarget(step.target)?.contains(event.target as Node)) window.setTimeout(next, 0);
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    };
    document.addEventListener("click", guard, true);
    return () => document.removeEventListener("click", guard, true);
  }, [step, next]);

  // Focus the guide card on each step, then hand focus to the highlighted control.
  useEffect(() => {
    if (!step) return;
    cardRef.current?.focus({ preventScroll: true });
    const timer = window.setTimeout(() => {
      const element = findTarget(step.target);
      const focusable = element?.matches("a[href],button,input,select,textarea,summary,[tabindex]") ? element : element?.querySelector<HTMLElement>("a[href],button,input,select,textarea,summary");
      if (focusable && document.activeElement === cardRef.current) focusable.focus({ preventScroll: true });
    }, 450);
    return () => window.clearTimeout(timer);
  }, [step, stepKey]);

  const exit = useCallback(() => dispatch({ type: "exit" }), [dispatch]);
  useEffect(() => {
    if (state.status === "idle") return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); exit(); }
      if (event.key === "Enter" && step?.advanceOn.type === "manual" && cardRef.current?.contains(document.activeElement) && document.activeElement === cardRef.current) next();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [state.status, step, exit, next]);

  const start = useCallback((chosen: Tour, allowActions: boolean) => {
    const roles = auth.status === "authenticated" ? auth.roleHints : [];
    const entry: TourEntry = !chosen.role || roles.includes(chosen.role) ? "direct" : auth.status === "authenticated" ? "switch" : "sign-in";
    dispatch({ type: "start", tourId: chosen.id, allowActions, entry });
  }, [auth, dispatch]);
  const value = useMemo<SimulationContextValue>(() => ({ state, tours, sampleBackend, openPicker: () => dispatch({ type: "pick" }), start, exit }), [state, tours, sampleBackend, dispatch, start, exit]);

  return (
    <SimulationContext.Provider value={value}>
      {children}
      {state.status === "picking" && <TourPicker />}
      {running && step && (
        <>
          <SimulationOverlay box={target.box} reducedMotion={reducedMotion} />
          <GuideCard
            ref={cardRef}
            step={step}
            index={Math.min(state.index, steps.length - 1)}
            total={steps.length}
            box={target.box}
            mobile={mobile}
            waiting={!target.element}
            onBack={() => dispatch({ type: "back" })}
            onSkip={next}
            onNext={next}
            onExit={exit}
          />
        </>
      )}
      {state.status === "done" && tour && (
        <SummaryCard tour={tour} onRestart={() => dispatch({ type: "restart" })} onAnother={() => dispatch({ type: "pick" })} onExit={exit} />
      )}
    </SimulationContext.Provider>
  );
}
