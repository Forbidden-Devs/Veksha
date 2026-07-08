/**
 * wsProxy.ts — WebSocket for session windows (training/lesson).
 *
 * On the Firefox build, extension-page WebSockets can get blocked by the
 * environment (profile security settings block plain ws:// from popup
 * panels even for loopback, NS_ERROR_CONTENT_BLOCKED), while the background
 * event page opens them reliably. So there the socket lives in the
 * background, bridged to the page over a runtime Port. Chrome popups open
 * ws:// to loopback fine, and its background is a service worker with a
 * limited lifetime — so Chrome and the web app use a raw WebSocket.
 *
 * The returned object mirrors the WebSocket surface the session windows use:
 * send/close, readyState, onopen/onmessage/onclose/onerror.
 */

export interface SessionSocket {
  send(data: string): void;
  close(): void;
  readyState: number;
  onopen: (() => void) | null;
  onmessage: ((e: { data: string }) => void) | null;
  onclose: (() => void) | null;
  onerror: (() => void) | null;
}

const OPEN = WebSocket.OPEN;
const CLOSED = WebSocket.CLOSED;

class PortSocket implements SessionSocket {
  readyState: number = WebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  private port: chrome.runtime.Port;

  constructor(url: string) {
    this.port = chrome.runtime.connect({ name: "veksha-ws" });
    this.port.onMessage.addListener((msg: { type: string; data?: string }) => {
      if (msg.type === "ws_open") {
        this.readyState = OPEN;
        this.onopen?.();
      } else if (msg.type === "ws_message") {
        this.onmessage?.({ data: msg.data ?? "" });
      } else if (msg.type === "ws_error") {
        this.onerror?.();
      } else if (msg.type === "ws_close") {
        this.readyState = CLOSED;
        this.onclose?.();
        this.port.disconnect();
      }
    });
    this.port.onDisconnect.addListener(() => {
      if (this.readyState !== CLOSED) {
        this.readyState = CLOSED;
        this.onclose?.();
      }
    });
    this.port.postMessage({ type: "ws_connect", url });
  }

  send(data: string): void {
    this.port.postMessage({ type: "ws_send", data });
  }

  close(): void {
    if (this.readyState === CLOSED) return;
    this.readyState = CLOSED;
    try { this.port.postMessage({ type: "ws_close" }); } catch { /* port already gone */ }
    try { this.port.disconnect(); } catch { /* ignore */ }
  }
}

class RawSocket implements SessionSocket {
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  private ws: WebSocket;

  constructor(url: string) {
    this.ws = new WebSocket(url);
    this.ws.onopen = () => this.onopen?.();
    this.ws.onmessage = (e) => this.onmessage?.({ data: e.data as string });
    this.ws.onclose = () => this.onclose?.();
    this.ws.onerror = () => this.onerror?.();
  }

  get readyState(): number { return this.ws.readyState; }
  send(data: string): void { this.ws.send(data); }
  close(): void { this.ws.close(); }
}

/** Open a backend session socket appropriate for the current context.
 *  (__BROWSER__ is defined by the extension build; the web app has no such
 *  define — `typeof` keeps the check safe there.) */
export function createSessionSocket(url: string): SessionSocket {
  const isFirefoxExtension =
    typeof __BROWSER__ !== "undefined" && __BROWSER__ === "firefox" &&
    typeof chrome !== "undefined" && !!chrome.runtime?.id;
  return isFirefoxExtension ? new PortSocket(url) : new RawSocket(url);
}
