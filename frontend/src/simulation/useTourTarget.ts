import { useEffect, useRef, useState } from "react";
import { findAny, findTarget } from "./engine";
import type { Box } from "./placement";

export interface TourTarget {
  element: HTMLElement | null;
  box: Box | null;
}

const PAD = 6;

function union(elements: HTMLElement[]): Box | null {
  const rects = elements.map((element) => element.getBoundingClientRect()).filter((rect) => rect.width > 0 && rect.height > 0);
  if (!rects.length) return null;
  const top = Math.min(...rects.map((rect) => rect.top)) - PAD;
  const left = Math.min(...rects.map((rect) => rect.left)) - PAD;
  const bottom = Math.max(...rects.map((rect) => rect.bottom)) + PAD;
  const right = Math.max(...rects.map((rect) => rect.right)) + PAD;
  return { top, left, width: right - left, height: bottom - top };
}

/** Nearest scrolling ancestor below the page that hides part of the element. */
function clippedBy(element: HTMLElement): HTMLElement | null {
  const own = element.getBoundingClientRect();
  for (let node = element.parentElement; node && node !== document.body && node !== document.documentElement; node = node.parentElement) {
    const style = getComputedStyle(node);
    const box = node.getBoundingClientRect();
    const vertical = /(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight && (own.top < box.top || own.bottom > box.bottom);
    const horizontal = /(auto|scroll)/.test(style.overflowX) && node.scrollWidth > node.clientWidth && (own.left < box.left || own.right > box.right);
    if (vertical || horizontal) return node;
  }
  return null;
}

const sameBox = (a: Box | null, b: Box | null) =>
  a === b || (!!a && !!b && Math.abs(a.top - b.top) < 0.5 && Math.abs(a.left - b.left) < 0.5 && Math.abs(a.width - b.width) < 0.5 && Math.abs(a.height - b.height) < 0.5);

/**
 * Tracks the highlighted element for the active step. When it exists but is hidden it opens the
 * enclosing disclosure or the phone navigation drawer, then scrolls it into view once.
 */
export function useTourTarget(
  id: string | null,
  extra: string[] = [],
  { stepKey, mobile, reducedMotion, assist }: { stepKey: string; mobile: boolean; reducedMotion: boolean; assist: (run: () => void) => void },
): TourTarget {
  const [target, setTarget] = useState<TourTarget>({ element: null, box: null });
  const scrolledFor = useRef<string | null>(null);
  const lastAssist = useRef(0);
  const lastScroll = useRef(0);
  const extraKey = extra.join(" ");
  useEffect(() => {
    if (!id) {
      setTarget({ element: null, box: null });
      return;
    }
    let frame = 0;
    const tick = () => {
      const element = findTarget(id);
      if (!element) {
        const hidden = findAny(id);
        const now = Date.now();
        if (hidden && now - lastAssist.current > 600) {
          lastAssist.current = now;
          const closed = hidden.closest<HTMLDetailsElement>("details:not([open])");
          const drawerToggle = document.querySelector<HTMLElement>('[data-tour="menu-toggle"][aria-expanded="false"]');
          if (closed) assist(() => { closed.open = true; });
          else if (mobile && hidden.closest("#workspace-navigation, .workspace-sidebar") && drawerToggle) assist(() => drawerToggle.click());
        }
        setTarget((current) => (current.element ? { element: null, box: null } : current));
      } else {
        const bottomInset = mobile ? window.innerHeight * 0.42 : 16;
        const now = Date.now();
        const clipped = clippedBy(element);
        if (clipped && now - lastScroll.current > 400) {
          lastScroll.current = now;
          const box = clipped.getBoundingClientRect(), own = element.getBoundingClientRect();
          if (own.top < box.top || own.bottom > box.bottom) clipped.scrollTop += own.top + own.height / 2 - (box.top + box.height / 2);
          if (own.left < box.left || own.right > box.right) clipped.scrollLeft += own.left + own.width / 2 - (box.left + box.width / 2);
        }
        const rect = element.getBoundingClientRect();
        const outside = rect.top < 80 || rect.bottom > window.innerHeight - bottomInset;
        if (scrolledFor.current !== stepKey || (outside && now - lastScroll.current > 400)) {
          scrolledFor.current = stepKey;
          lastScroll.current = now;
          if (outside) {
            const room = window.innerHeight - 80 - bottomInset;
            const offset = rect.height > room ? rect.top - 96 : rect.top + rect.height / 2 - (80 + room / 2);
            window.scrollBy?.({ top: offset, behavior: reducedMotion ? "auto" : "instant" });
          }
        }
        const others = extraKey ? extraKey.split(" ").map(findTarget).filter((item): item is HTMLElement => !!item) : [];
        const box = union([element, ...others]);
        setTarget((current) => (current.element === element && sameBox(current.box, box) ? current : { element, box }));
      }
      frame = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(frame);
  }, [id, extraKey, stepKey, mobile, reducedMotion, assist]);
  return target;
}
