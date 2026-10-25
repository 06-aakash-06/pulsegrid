import { forwardRef, useLayoutEffect, useRef, useState, type ForwardedRef } from "react";
import { createPortal } from "react-dom";
import { dockSheet, placeCard, type Box } from "./placement";
import type { Tour, TourStep } from "./types";

const HEADER_INSET = 76;

function mergeRefs<T>(...refs: (ForwardedRef<T> | undefined)[]) {
  return (value: T | null) => {
    for (const ref of refs) {
      if (typeof ref === "function") ref(value);
      else if (ref) ref.current = value;
    }
  };
}

interface GuideCardProps {
  step: TourStep;
  index: number;
  total: number;
  box: Box | null;
  mobile: boolean;
  waiting: boolean;
  onBack: () => void;
  onSkip: () => void;
  onNext: () => void;
  onExit: () => void;
}

export const GuideCard = forwardRef<HTMLDivElement, GuideCardProps>(function GuideCard({ step, index, total, box, mobile, waiting, onBack, onSkip, onNext, onExit }, ref) {
  const own = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 340, height: 220 });
  useLayoutEffect(() => {
    const element = own.current;
    if (!element) return;
    const measure = () => setSize((current) => {
      const next = { width: element.offsetWidth || 340, height: element.offsetHeight || 220 };
      return current.width === next.width && current.height === next.height ? current : next;
    });
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    return () => observer?.disconnect();
  }, [step.id]);
  const viewport = { width: typeof window === "undefined" ? 1280 : window.innerWidth, height: typeof window === "undefined" ? 800 : window.innerHeight };
  const dock = mobile ? dockSheet(box, size.height, viewport.height) : null;
  const position = mobile ? null : placeCard(box, size, viewport, HEADER_INSET);
  const titleId = `simulation-step-${step.id}`;
  return createPortal(
    <div
      ref={mergeRefs(own, ref)}
      className={`simulation-card${dock ? ` simulation-card--sheet simulation-card--${dock}` : ""}`}
      style={position ? { top: position.top, left: position.left } : undefined}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      aria-live="polite"
      tabIndex={-1}
      data-simulation-card
      data-sim-step={index + 1}
      data-sim-total={total}
      data-sim-target={step.target}
      data-sim-advance={step.advanceOn.type}
      {...(step.suggestion ? { "data-sim-fill": step.suggestion } : {})}
      {...(step.choose ? { "data-sim-choose": step.choose } : {})}
    >
      <p className="simulation-card__count">Step {index + 1} of {total}</p>
      <h2 id={titleId}>{step.title}</h2>
      <p>{step.body}</p>
      {step.suggestion && <p className="simulation-card__hint">Try typing: <q>{step.suggestion}</q></p>}
      {waiting && <p className="simulation-card__hint" role="status">Waiting for this part of the page to appear…</p>}
      {step.behindTheScenes && (
        <details className="simulation-card__explain">
          <summary>What's happening behind the scenes?</summary>
          <p>{step.behindTheScenes}</p>
        </details>
      )}
      <div className="simulation-card__actions">
        <button type="button" onClick={onBack} disabled={index === 0}>Back</button>
        {step.advanceOn.type === "manual"
          ? <button type="button" className="simulation-card__primary" onClick={onNext} data-sim-next>Next</button>
          : <button type="button" onClick={onSkip}>Skip step</button>}
        <button type="button" onClick={onExit}>Exit</button>
      </div>
    </div>,
    document.body,
  );
});

export function SummaryCard({ tour, onRestart, onAnother, onExit }: { tour: Tour; onRestart: () => void; onAnother: () => void; onExit: () => void }) {
  const first = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => first.current?.focus(), []);
  return createPortal(
    <div className="simulation-backdrop" data-simulation-summary>
      <div className="simulation-card simulation-card--summary" role="dialog" aria-modal="true" aria-labelledby="simulation-summary-title" aria-live="polite">
        <p className="simulation-card__count">Walkthrough complete</p>
        <h2 id="simulation-summary-title">{tour.title}</h2>
        <p>{tour.summary}</p>
        <div className="simulation-card__actions">
          <button ref={first} type="button" className="simulation-card__primary" onClick={onRestart}>Restart</button>
          <button type="button" onClick={onAnother}>Try another role</button>
          <button type="button" onClick={onExit}>Exit</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
