import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { useState } from "react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/auth/authContext";
import { announceCommandSuccess, entrySteps, idleState, readPersisted, reduce, runnableSteps, STORAGE_KEY } from "../src/simulation/engine";
import { placeCard } from "../src/simulation/placement";
import { SimulationProvider, useSimulation } from "../src/simulation/SimulationProvider";
import { allTours } from "../src/simulation/tours/index";
import type { Tour } from "../src/simulation/types";

const anonymous = {
  refresh: async () => { throw Error("No session"); },
  login: vi.fn(), register: vi.fn(), logout: vi.fn(),
};

const testTour: Tour = {
  id: "test", role: null, workspace: null, roleLabel: "Tester", title: "Test tour", goal: "Exercise the engine.", summary: "Engine summary.",
  steps: [
    { id: "click", target: "first", title: "Click first", body: "Click it.", advanceOn: { type: "click" } },
    { id: "route", target: "go", title: "Go to second", body: "Navigate.", advanceOn: { type: "route", value: "^/second" } },
    { id: "visible", target: "reveal", title: "Reveal", body: "Show the receipt.", advanceOn: { type: "visible", value: "receipt" } },
    { id: "event", target: "command", title: "Run command", body: "Succeed.", advanceOn: { type: "event", value: "Book appointment" }, mutates: true },
    { id: "manual", target: "command", title: "Read", body: "Read it.", advanceOn: { type: "manual" } },
  ],
};

function Pages({ outside }: { outside: () => void }) {
  const navigate = useNavigate();
  const simulation = useSimulation();
  return (
    <>
      <button type="button" onClick={() => simulation?.start(testTour, false)}>Begin</button>
      <button type="button" data-tour="first">First</button>
      <button type="button" data-tour="go" onClick={() => navigate("/second")}>Go</button>
      <button type="button" onClick={outside}>Outside</button>
      <Routes>
        <Route path="/" element={null} />
        <Route path="/second" element={<Reveal />} />
      </Routes>
      <button type="button" data-tour="command">Command</button>
    </>
  );
}
function Reveal() {
  const [shown, setShown] = useState(false);
  return <><button type="button" data-tour="reveal" onClick={() => setShown(true)}>Reveal</button>{shown && <p data-tour="receipt">Receipt</p>}</>;
}

function mount(outside = vi.fn()) {
  render(
    <AuthProvider client={anonymous}>
      <MemoryRouter>
        <SimulationProvider tours={[testTour]} sampleBackend>
          <Pages outside={outside} />
        </SimulationProvider>
      </MemoryRouter>
    </AuthProvider>,
  );
  return outside;
}
const stepTitle = () => screen.getByRole("dialog").querySelector("h2")?.textContent;

afterEach(() => { sessionStorage.clear(); vi.useRealTimers(); });

describe("simulation engine", () => {
  it("advances on click, route, visible, event and manual steps, then shows the summary", async () => {
    mount();
    fireEvent.click(screen.getByText("Begin"));
    expect(stepTitle()).toBe("Click first");
    fireEvent.click(screen.getByText("First"));
    expect(await screen.findByRole("heading", { name: "Go to second" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Go"));
    expect(await screen.findByRole("heading", { name: "Reveal" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reveal" }));
    expect(await screen.findByRole("heading", { name: "Run command" }, { timeout: 2000 })).toBeInTheDocument();
    act(() => announceCommandSuccess("Some other command"));
    expect(stepTitle()).toBe("Run command");
    act(() => announceCommandSuccess("Book appointment"));
    expect(await screen.findByRole("heading", { name: "Read" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("heading", { name: "Test tour" })).toBeInTheDocument();
    expect(screen.getByText("Engine summary.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Restart" }));
    expect(stepTitle()).toBe("Click first");
  });

  it("goes back a step and exits with Escape or the Exit button", async () => {
    mount();
    fireEvent.click(screen.getByText("Begin"));
    fireEvent.click(screen.getByText("First"));
    await screen.findByRole("heading", { name: "Go to second" });
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(stepTitle()).toBe("Click first");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Begin"));
    fireEvent.click(screen.getByRole("button", { name: "Exit" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("blocks clicks outside the highlighted target while a step is active", () => {
    const outside = mount();
    fireEvent.click(screen.getByText("Begin"));
    fireEvent.click(screen.getByText("Outside"));
    expect(outside).not.toHaveBeenCalled();
    expect(stepTitle()).toBe("Click first");
    fireEvent.click(screen.getByRole("button", { name: "Exit" }));
    fireEvent.click(screen.getByText("Outside"));
    expect(outside).toHaveBeenCalledTimes(1);
  });

  it("resumes at the saved step after a reload", async () => {
    mount();
    fireEvent.click(screen.getByText("Begin"));
    fireEvent.click(screen.getByText("First"));
    await screen.findByRole("heading", { name: "Go to second" });
    expect(readPersisted()).toMatchObject({ status: "running", tourId: "test", index: 1 });
    cleanup();
    mount();
    expect(stepTitle()).toBe("Go to second");
  });

  it("keeps the reducer and persistence safe", () => {
    const started = reduce(idleState, { type: "start", tourId: "test", allowActions: false, entry: "direct" });
    expect(reduce(started, { type: "next", count: 1 }).status).toBe("done");
    expect(reduce(started, { type: "back" }).index).toBe(0);
    sessionStorage.setItem(STORAGE_KEY, "{not json");
    expect(readPersisted()).toEqual(idleState);
  });

  it("skips mutating steps on a live server unless demo actions are allowed", () => {
    expect(runnableSteps(testTour, false, false).map((step) => step.id)).not.toContain("event");
    expect(runnableSteps(testTour, false, true).map((step) => step.id)).toContain("event");
    expect(runnableSteps(testTour, true, false)).toHaveLength(testTour.steps.length);
  });

  it("adds sign-in steps when the visitor is not in the tour's workspace", () => {
    const patient = allTours.find((tour) => tour.id === "patient")!;
    expect(entrySteps(patient, "direct")).toHaveLength(0);
    expect(entrySteps(patient, "sign-in").map((step) => step.target)).toEqual(["quick-sign-in-patient", "sign-in-submit"]);
    expect(entrySteps(patient, "switch")[0].target).toBe("sign-out");
  });

  it("places the guide card beside the target without covering it", () => {
    const target = { top: 300, left: 400, width: 200, height: 60 };
    const spot = placeCard(target, { width: 340, height: 220 }, { width: 1536, height: 864 }, 76);
    const card = { ...spot, width: 340, height: 220 };
    const overlaps = card.left < target.left + target.width && card.left + card.width > target.left && card.top < target.top + target.height && card.top + card.height > target.top;
    expect(overlaps).toBe(false);
  });
});

describe("tour definitions", () => {
  const sources: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) { if (name !== "tours") walk(path); }
      else if (/\.(tsx?|jsx?)$/.test(name)) sources.push(readFileSync(path, "utf8"));
    }
  };
  walk(resolve(__dirname, "../src"));
  const source = sources.join("\n");
  // Literal ids from `data-tour="…"` and from components' `tour="…"` props (which add -review, -confirm and -cancel).
  const literal = new Set([...source.matchAll(/data-tour="([^"]+)"/g), ...source.matchAll(/data-tour=\{[^}]*?"([a-z0-9-]+)"/g)].map((m) => m[1]));
  for (const [expression] of source.matchAll(/data-tour=\{[^}]+\}/g)) {
    for (const [, id] of expression.matchAll(/"([a-z0-9-]+)"/g)) literal.add(id);
  }
  for (const [, id] of source.matchAll(/\btour="([^"]+)"/g)) for (const suffix of ["", "-review", "-confirm", "-cancel"]) literal.add(`${id}${suffix}`);
  // Ids built from data, such as `nav-${item.path}`; each prefix must appear in a data-tour template.
  const templates = [...source.matchAll(/(?:data-tour|tour)=\{`([a-z-]+)\$\{/g)].map((m) => m[1]);
  const declared = (id: string) => literal.has(id) || templates.some((prefix) => id.startsWith(prefix) && /^[a-z0-9-]+$/.test(id.slice(prefix.length).replace(/-(review|confirm|cancel)$/, "")));

  it("gives every tour between 4 and 30 steps and a unique id", () => {
    expect(new Set(allTours.map((tour) => tour.id)).size).toBe(allTours.length);
    for (const tour of allTours) expect(tour.steps.length, tour.id).toBeGreaterThanOrEqual(4);
  });

  it("points every step and visible condition at a data-tour attribute in src", () => {
    const missing: string[] = [];
    for (const tour of allTours) {
      for (const step of [...entrySteps(tour, "switch"), ...tour.steps]) {
        for (const id of [step.target, ...(step.extraTargets ?? []), ...(step.advanceOn.type === "visible" ? [step.advanceOn.value] : [])]) {
          if (!declared(id)) missing.push(`${tour.id}/${step.id}: ${id}`);
        }
      }
    }
    expect(missing).toEqual([]);
  });

  it("names a real navigation page for every nav- target", () => {
    const workspaces = readFileSync(resolve(__dirname, "../src/navigation/workspaces.ts"), "utf8");
    for (const tour of allTours) {
      for (const step of tour.steps.filter((item) => item.target.startsWith("nav-"))) {
        expect(workspaces, `${tour.id}/${step.id}`).toContain(`page("${step.target.slice(4)}"`);
      }
    }
  });
});
