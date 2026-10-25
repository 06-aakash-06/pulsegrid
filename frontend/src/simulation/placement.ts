export interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const GAP = 14;
const MARGIN = 16;

const overlaps = (a: Box, b: Box) =>
  a.left < b.left + b.width && a.left + a.width > b.left && a.top < b.top + b.height && a.top + a.height > b.top;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), Math.max(min, max));

/** Places the card beside the target without covering it: below, above, right, left, then a free corner. */
export function placeCard(target: Box | null, card: { width: number; height: number }, viewport: { width: number; height: number }, topInset = 0): { top: number; left: number } {
  const maxLeft = viewport.width - card.width - MARGIN;
  const maxTop = viewport.height - card.height - MARGIN;
  if (!target) return { top: clamp((viewport.height - card.height) / 2, topInset + MARGIN, maxTop), left: clamp((viewport.width - card.width) / 2, MARGIN, maxLeft) };
  const centredLeft = clamp(target.left + target.width / 2 - card.width / 2, MARGIN, maxLeft);
  const centredTop = clamp(target.top + target.height / 2 - card.height / 2, topInset + MARGIN, maxTop);
  const candidates = [
    { top: target.top + target.height + GAP, left: centredLeft },
    { top: target.top - card.height - GAP, left: centredLeft },
    { top: centredTop, left: target.left + target.width + GAP },
    { top: centredTop, left: target.left - card.width - GAP },
    { top: maxTop, left: maxLeft },
    { top: topInset + MARGIN, left: maxLeft },
    { top: maxTop, left: MARGIN },
    { top: topInset + MARGIN, left: MARGIN },
  ];
  const fits = (spot: { top: number; left: number }) =>
    spot.top >= topInset + MARGIN && spot.left >= MARGIN && spot.top <= maxTop && spot.left <= maxLeft &&
    !overlaps({ ...spot, width: card.width, height: card.height }, target);
  return candidates.find(fits) ?? candidates[4];
}

/** On phones the card docks as a sheet; it moves to the top edge when the target sits under the bottom sheet. */
export function dockSheet(target: Box | null, sheetHeight: number, viewportHeight: number): "bottom" | "top" {
  if (!target) return "bottom";
  return target.top + target.height > viewportHeight - sheetHeight - 8 ? "top" : "bottom";
}
