import { useId } from "react";
import type { Box } from "./placement";

/** Dim layer with a spotlight cut-out; four transparent blockers catch clicks around the hole. */
export function SimulationOverlay({ box, reducedMotion }: { box: Box | null; reducedMotion: boolean }) {
  const mask = useId().replace(/:/g, "");
  const width = typeof window === "undefined" ? 0 : window.innerWidth;
  const height = typeof window === "undefined" ? 0 : window.innerHeight;
  const hole = box ?? { top: 0, left: 0, width: 0, height: 0 };
  const blockers = box
    ? [
        { top: 0, left: 0, width, height: Math.max(0, hole.top) },
        { top: hole.top + hole.height, left: 0, width, height: Math.max(0, height - hole.top - hole.height) },
        { top: hole.top, left: 0, width: Math.max(0, hole.left), height: hole.height },
        { top: hole.top, left: hole.left + hole.width, width: Math.max(0, width - hole.left - hole.width), height: hole.height },
      ]
    : [{ top: 0, left: 0, width, height }];
  return (
    <div className="simulation-overlay" data-simulation-overlay aria-hidden="true">
      <svg className="simulation-overlay__dim" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <mask id={mask}>
            <rect width={width} height={height} fill="white" />
            {box && <rect x={hole.left} y={hole.top} width={hole.width} height={hole.height} rx="10" fill="black" />}
          </mask>
        </defs>
        <rect width={width} height={height} fill="currentColor" mask={`url(#${mask})`} />
      </svg>
      {box && <div className={`simulation-ring${reducedMotion ? "" : " simulation-ring--pulse"}`} style={{ top: hole.top, left: hole.left, width: hole.width, height: hole.height }} />}
      {blockers.map((blocker, index) => (
        <div key={index} className="simulation-blocker" style={blocker} onPointerDown={(event) => event.preventDefault()} />
      ))}
    </div>
  );
}
