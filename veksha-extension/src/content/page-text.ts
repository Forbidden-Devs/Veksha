/**
 * page-text.ts — shared page-text filtering rules.
 *
 * Used by Reading Coach and vocabulary tracking.
 * vocabfreq.ts (one-shot whole-page sampling) so the "what counts as
 * readable content" rules live in one place.
 */

export const SKIP_TAGS = new Set([
  "SCRIPT", "STYLE", "NOSCRIPT", "TEXTAREA", "INPUT", "SELECT", "OPTION",
  "CODE", "PRE", "KBD", "SAMP", "BUTTON", "SVG", "CANVAS", "MATH", "TITLE",
]);

// Our own injected UI — never read text inside it.
export const SKIP_CLOSEST =
  ".vk-assistant-card, .vk-selection-tools, .vk-page-reminder, #veksha-page-workspace, .av-yt-layer, .av-imm, .av-grammar, [data-av-skip]";

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

function isReadable(text: string, minChars: number): boolean {
  const trimmed = text.trim();
  if (trimmed.length < minChars) return false;
  if (!/\p{L}/u.test(trimmed)) return false;
  return /\s/.test(trimmed);
}

/** One-shot whole-page text sample, up to `budget` chars, for features that
 *  analyze a page once (CI Meter, vocab frequency) rather than continuously
 */
export function sampleText(budget: number, minChars = 40): string {
  const parts: string[] = [];
  let total = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node: Node): number {
      const text = node as Text;
      const parent = text.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      if (SKIP_TAGS.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
      if (parent.isContentEditable) return NodeFilter.FILTER_REJECT;
      if (parent.closest(SKIP_CLOSEST)) return NodeFilter.FILTER_REJECT;
      if (!isReadable(text.data, minChars)) return NodeFilter.FILTER_REJECT;
      if (!isVisible(parent)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  while (total < budget && walker.nextNode()) {
    const text = (walker.currentNode as Text).data.trim();
    parts.push(text);
    total += text.length;
  }
  return parts.join("\n");
}
