import React, { useLayoutEffect, useRef, useState } from "react";
import { createRoot, Root } from "react-dom/client";
import { TrainingWindow } from "../popup/overlays/TrainingWindow";
import { LessonWindow } from "../popup/overlays/LessonWindow";
import { I18nProvider } from "../shared/i18n";
import rawPaletteCss from "../shared/palette.css?inline";
import rawPopupCss from "../popup/popup.css?inline";

// In Shadow DOM :root doesn't resolve to the document root, use :host instead.
// Also override lesson-overlay positioning which is designed for the in-popup context.
const SHADOW_CSS =
  `${rawPaletteCss}\n${rawPopupCss}`.replace(/:root/g, ":host") +
  `
  /* === page-overlay context overrides === */
  .training-window, .lesson-overlay {
    flex: 1 1 0;
    min-height: 0;
    position: static !important;
    inset: unset !important;
    width: 100% !important;
    height: auto !important;
    z-index: unset !important;
  }
  /* Fit-content overlays (e.g. training): don't stretch the child to fill a
     fixed height — size the window to its content so there's no dead space. */
  .av-overlay-auto .training-window {
    flex: 0 0 auto !important;
  }
  `;

let shadowHost: HTMLElement | null = null;
let overlayRoot: Root | null = null;

function getShadowContainer(): HTMLElement {
  if (!shadowHost) {
    shadowHost = document.createElement("div");
    shadowHost.id = "veksha-overlay-host";
    // Host has no layout impact
    shadowHost.style.cssText = "position:fixed;top:0;left:0;width:0;height:0;pointer-events:none;z-index:2147483646;";
    document.documentElement.appendChild(shadowHost);
  }

  const shadow = shadowHost.shadowRoot ?? shadowHost.attachShadow({ mode: "open" });

  let style = shadow.querySelector("style#av-css") as HTMLStyleElement | null;
  if (!style) {
    style = document.createElement("style");
    style.id = "av-css";
    style.textContent = SHADOW_CSS;
    shadow.appendChild(style);
  }

  let container = shadow.querySelector("#av-container") as HTMLElement | null;
  if (!container) {
    container = document.createElement("div");
    container.id = "av-container";
    container.style.cssText = "pointer-events:auto;";
    shadow.appendChild(container);
  }

  return container;
}

export function showTrainingOverlay(username: string): void {
  const container = getShadowContainer();
  overlayRoot?.unmount();
  overlayRoot = createRoot(container);
  overlayRoot.render(
    <I18nProvider>
      <PageOverlay initWidth={460} initHeight={580} autoHeight>
        <TrainingWindow username={username} onClose={closeOverlay} />
      </PageOverlay>
    </I18nProvider>
  );
}

export function showLessonOverlay(username: string, topic: string): void {
  const container = getShadowContainer();
  overlayRoot?.unmount();
  overlayRoot = createRoot(container);
  overlayRoot.render(
    <I18nProvider>
      <PageOverlay initWidth={700} initHeight={720}>
        <LessonWindow username={username} topicName={topic} onClose={closeOverlay} />
      </PageOverlay>
    </I18nProvider>
  );
}

export function closeOverlay(): void {
  overlayRoot?.unmount();
  overlayRoot = null;
}

// ---------------------------------------------------------------------------
// PageOverlay — draggable by [data-drag-handle], resizable via CSS resize
// ---------------------------------------------------------------------------

function PageOverlay({
  children,
  initWidth,
  initHeight,
  autoHeight = false,
}: {
  children: React.ReactNode;
  initWidth: number;
  initHeight: number;
  autoHeight?: boolean;
}) {
  const [pos, setPos] = useState(() => ({
    x: Math.max(20, Math.round((window.innerWidth - initWidth) / 2)),
    y: 60,
  }));
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null);

  // Set initial size imperatively so CSS resize can change it freely
  // without React overriding it on re-renders.
  useLayoutEffect(() => {
    if (ref.current) {
      ref.current.style.width = `${initWidth}px`;
      if (autoHeight) {
        // Fit content; initHeight becomes a cap so tall content still fits the screen.
        ref.current.style.height = "auto";
        ref.current.style.maxHeight = `min(${initHeight}px, calc(100vh - 80px))`;
      } else {
        ref.current.style.height = `${initHeight}px`;
      }
    }
  }, []);

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    const target = e.target as HTMLElement;
    if (target.closest("button, input, textarea, select")) return;
    if (!target.closest("[data-drag-handle]")) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { sx: e.clientX, sy: e.clientY, px: pos.x, py: pos.y };
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    setPos({
      x: Math.max(0, drag.current.px + e.clientX - drag.current.sx),
      y: Math.max(0, drag.current.py + e.clientY - drag.current.sy),
    });
  }

  function onPointerUp() {
    drag.current = null;
  }

  return (
    <div
      ref={ref}
      className={autoHeight ? "av-overlay-auto" : undefined}
      // Keyboard events are composed, so they cross the Shadow DOM boundary
      // unless we stop them here.  Let child controls handle the event first
      // (including TrainingWindow's Enter shortcut), then keep it away from
      // host-page shortcuts such as YouTube's Space and GitHub's A/C/L keys.
      onKeyDown={(e) => e.stopPropagation()}
      onKeyUp={(e) => e.stopPropagation()}
      onKeyPress={(e) => e.stopPropagation()}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      style={{
        position: "fixed",
        left: pos.x,
        top: pos.y,
        resize: "both",
        overflow: "hidden",
        zIndex: 2147483647,
        display: "flex",
        flexDirection: "column",
        borderRadius: 16,
        boxShadow: "0 12px 40px rgba(43,36,56,0.35)",
        border: "1px solid #ece8f6",
        background: "#fff",
        minWidth: 300,
        minHeight: 250,
        fontFamily: '-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif',
        color: "#2b2438",
      }}
    >
      {children}
    </div>
  );
}
