import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { LessonWindow } from "../popup/overlays/LessonWindow";
import { PracticePlannerWindow } from "../popup/overlays/PracticePlannerWindow";
import rawPopupCss from "../popup/popup.css?inline";
import { I18nProvider } from "../shared/i18n";
import rawPaletteCss from "../shared/palette.css?inline";

const PAGE_WINDOW_CSS = `
  :host {
    position: fixed;
    inset: 0;
    z-index: 2147483646;
    pointer-events: none;
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }

  * { box-sizing: border-box; }

  .vk-page-window {
    position: fixed;
    z-index: 1;
    display: flex;
    min-width: min(320px, calc(100vw - 24px));
    min-height: 240px;
    max-width: calc(100vw - 24px);
    max-height: calc(100vh - 24px);
    overflow: hidden;
    resize: both;
    border: 1px solid color-mix(in srgb, var(--m-accent-2) 28%, var(--m-border));
    border-radius: 18px;
    background: var(--m-surface);
    box-shadow: 0 24px 70px color-mix(in srgb, var(--m-fg) 25%, transparent);
    color: var(--m-fg);
    pointer-events: auto;
    isolation: isolate;
  }

  .vk-page-window::before {
    content: "";
    position: absolute;
    inset: 0 0 auto;
    z-index: 4;
    height: 3px;
    background: linear-gradient(90deg, var(--m-accent-2), var(--m-accent));
    pointer-events: none;
  }

  .vk-page-window.is-content-sized {
    height: auto !important;
    resize: horizontal;
  }

  .vk-page-window > .training-window,
  .vk-page-window > .lesson-overlay {
    position: static !important;
    inset: auto !important;
    flex: 1 1 auto;
    width: 100% !important;
    height: auto !important;
    min-height: 0;
    border: 0 !important;
    border-radius: inherit;
    box-shadow: none !important;
  }

  .vk-page-window.is-content-sized > .training-window {
    flex: 0 0 auto;
  }

  @media (max-width: 520px) {
    .vk-page-window {
      left: 8px !important;
      width: calc(100vw - 16px) !important;
      max-width: none;
      border-radius: 14px;
      resize: vertical;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .vk-page-window { scroll-behavior: auto; }
  }
`;

const SHADOW_STYLES = `${rawPaletteCss.replace(/:root/g, ":host")}\n${rawPopupCss}\n${PAGE_WINDOW_CSS}`;

interface WindowSpec {
  width: number;
  height: number;
  contentSized?: boolean;
}

let host: HTMLElement | null = null;
let root: Root | null = null;
let themeListenerBound = false;

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), Math.max(low, high));
}

function syncHostTheme(name: unknown): void {
  if (host) host.dataset.vekshaTheme = String(name ?? "light");
}

function ensureRoot(): Root {
  if (!host) {
    host = document.createElement("div");
    host.id = "veksha-page-workspace";
    document.documentElement.appendChild(host);
  }
  const shadow = host.shadowRoot ?? host.attachShadow({ mode: "open" });
  let style = shadow.querySelector<HTMLStyleElement>("style[data-veksha-page-styles]");
  if (!style) {
    style = document.createElement("style");
    style.dataset.vekshaPageStyles = "true";
    style.textContent = SHADOW_STYLES;
    shadow.appendChild(style);
  }
  let mount = shadow.querySelector<HTMLElement>("[data-veksha-page-mount]");
  if (!mount) {
    mount = document.createElement("div");
    mount.dataset.vekshaPageMount = "true";
    shadow.appendChild(mount);
  }
  root ??= createRoot(mount);

  if (!themeListenerBound) {
    themeListenerBound = true;
    void chrome.storage.local.get(["vk_theme"]).then((values) => syncHostTheme(values.vk_theme));
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === "local" && changes.vk_theme) syncHostTheme(changes.vk_theme.newValue);
    });
  }
  return root;
}

function initialPosition(width: number): { x: number; y: number } {
  return {
    x: Math.max(12, Math.round((window.innerWidth - Math.min(width, window.innerWidth - 24)) / 2)),
    y: Math.max(12, Math.min(56, window.innerHeight - 260)),
  };
}

function FloatingWorkspace({ children, spec }: { children: ReactNode; spec: WindowSpec }) {
  const frame = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointerId: number; x: number; y: number; originX: number; originY: number } | null>(null);
  const [position, setPosition] = useState(() => initialPosition(spec.width));

  useLayoutEffect(() => {
    const element = frame.current;
    if (!element) return;
    element.style.width = `${Math.min(spec.width, window.innerWidth - 24)}px`;
    if (spec.contentSized) {
      element.style.maxHeight = `min(${spec.height}px, calc(100vh - 24px))`;
    } else {
      element.style.height = `${Math.min(spec.height, window.innerHeight - 24)}px`;
    }
  }, [spec.contentSized, spec.height, spec.width]);

  useEffect(() => {
    const keepInViewport = () => {
      const rect = frame.current?.getBoundingClientRect();
      if (!rect) return;
      setPosition((current) => ({
        x: clamp(current.x, 8, window.innerWidth - Math.min(rect.width, window.innerWidth - 16) - 8),
        y: clamp(current.y, 8, window.innerHeight - Math.min(rect.height, window.innerHeight - 16) - 8),
      }));
    };
    window.addEventListener("resize", keepInViewport);
    return () => window.removeEventListener("resize", keepInViewport);
  }, []);

  function beginDrag(event: PointerEvent<HTMLDivElement>): void {
    const target = event.target as HTMLElement;
    if (!target.closest("[data-drag-handle]") || target.closest("button, input, textarea, select, a")) return;
    drag.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      originX: position.x,
      originY: position.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveDrag(event: PointerEvent<HTMLDivElement>): void {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    const rect = frame.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({
      x: clamp(current.originX + event.clientX - current.x, 8, window.innerWidth - rect.width - 8),
      y: clamp(current.originY + event.clientY - current.y, 8, window.innerHeight - 44),
    });
  }

  function endDrag(event: PointerEvent<HTMLDivElement>): void {
    if (drag.current?.pointerId === event.pointerId) drag.current = null;
  }

  return (
    <div
      ref={frame}
      className={`vk-page-window${spec.contentSized ? " is-content-sized" : ""}`}
      style={{ left: position.x, top: position.y }}
      onPointerDown={beginDrag}
      onPointerMove={moveDrag}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={(event) => {
        if (event.key === "Escape") closeOverlay();
        event.stopPropagation();
      }}
      onKeyUp={(event) => event.stopPropagation()}
    >
      {children}
    </div>
  );
}

function renderWindow(content: ReactNode, spec: WindowSpec): void {
  ensureRoot().render(
    <I18nProvider>
      <FloatingWorkspace spec={spec}>{content}</FloatingWorkspace>
    </I18nProvider>,
  );
}

export function showTrainingOverlay(username: string): void {
  renderWindow(
    <PracticePlannerWindow username={username} onClose={closeOverlay} />,
    { width: 470, height: 680, contentSized: true },
  );
}

export function showLessonOverlay(username: string, topic: string): void {
  renderWindow(
    <LessonWindow username={username} topicName={topic} onClose={closeOverlay} />,
    { width: 720, height: 740 },
  );
}

export function closeOverlay(): void {
  root?.render(null);
}
