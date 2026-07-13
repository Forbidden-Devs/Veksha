/**
 * page-text.ts — shared page-text filtering rules.
 *
 * Used by immersion.ts (continuous viewport scanning) and cimeter.ts
 * (one-shot whole-page sampling) so the "what counts as readable content"
 * rules live in one place.
 */

export const SKIP_TAGS = new Set([
  "SCRIPT", "STYLE", "NOSCRIPT", "TEXTAREA", "INPUT", "SELECT", "OPTION",
  "CODE", "PRE", "KBD", "SAMP", "BUTTON", "SVG", "CANVAS", "MATH", "TITLE",
]);

// Our own injected UI — never read text inside it.
export const SKIP_CLOSEST =
  ".veksha-popup, .veksha-icon, .veksha-aggressive-reminder, .av-yt-layer, .av-imm, .av-grammar, [data-av-skip]";

export function isVisible(el: Element, margin = 0): boolean {
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return false;
  return (
    rect.bottom > -margin &&
    rect.top < window.innerHeight + margin &&
    rect.right > 0 &&
    rect.left < window.innerWidth
  );
}
