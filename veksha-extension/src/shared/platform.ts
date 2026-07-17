/**
 * platform.ts — thin abstraction over extension-only APIs so the popup app
 * can also run as a plain web app (veksha-web).
 *
 * Extension contexts use chrome.storage.local / chrome.runtime; the web build
 * falls back to localStorage and no-op messaging. Keep every chrome.* access
 * in UI code behind this module.
 */

export const isExtension: boolean =
  typeof chrome !== "undefined" && !!chrome.storage?.local;

const LS_PREFIX = "veksha:";

export async function storageGet(keys: string[]): Promise<Record<string, unknown>> {
  if (isExtension) {
    return chrome.storage.local.get(keys);
  }
  const out: Record<string, unknown> = {};
  for (const k of keys) {
    const raw = localStorage.getItem(LS_PREFIX + k);
    if (raw !== null) {
      try { out[k] = JSON.parse(raw); } catch { out[k] = raw; }
    }
  }
  return out;
}

export async function storageGetAll(): Promise<Record<string, unknown>> {
  if (isExtension) {
    return chrome.storage.local.get(null);
  }
  const out: Record<string, unknown> = {};
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (!k?.startsWith(LS_PREFIX)) continue;
    const raw = localStorage.getItem(k);
    if (raw === null) continue;
    const key = k.slice(LS_PREFIX.length);
    try { out[key] = JSON.parse(raw); } catch { out[key] = raw; }
  }
  return out;
}

export async function storageSet(items: Record<string, unknown>): Promise<void> {
  if (isExtension) {
    await chrome.storage.local.set(items);
    return;
  }
  for (const [k, v] of Object.entries(items)) {
    localStorage.setItem(LS_PREFIX + k, JSON.stringify(v));
  }
}

/** Session-scoped storage for transient UI state: survives the popup being
 *  closed (the browser kills the action popup on any focus loss), cleared
 *  when the browser exits. Web build falls back to window.sessionStorage. */
export async function sessionGet(keys: string[]): Promise<Record<string, unknown>> {
  if (isExtension && chrome.storage.session) {
    try { return await chrome.storage.session.get(keys); } catch { return {}; }
  }
  const out: Record<string, unknown> = {};
  for (const k of keys) {
    const raw = sessionStorage.getItem(LS_PREFIX + k);
    if (raw !== null) {
      try { out[k] = JSON.parse(raw); } catch { out[k] = raw; }
    }
  }
  return out;
}

export async function sessionSet(items: Record<string, unknown>): Promise<void> {
  if (isExtension && chrome.storage.session) {
    try { await chrome.storage.session.set(items); } catch { /* ignore */ }
    return;
  }
  for (const [k, v] of Object.entries(items)) {
    sessionStorage.setItem(LS_PREFIX + k, JSON.stringify(v));
  }
}

export async function storageRemove(keys: string[]): Promise<void> {
  if (isExtension) {
    await chrome.storage.local.remove(keys);
    return;
  }
  for (const k of keys) localStorage.removeItem(LS_PREFIX + k);
}

/** Subscribe to changes of a single key. Extension-only; no-op on web
 *  (the web app is a single context — module state stays authoritative). */
export function onStorageKeyChanged(key: string, cb: (newValue: unknown) => void): void {
  if (!isExtension) return;
  try {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === "local" && changes[key]) cb(changes[key].newValue);
    });
  } catch { /* ignore */ }
}

/** Fire-and-forget message to the extension runtime; no-op on web. */
export function runtimeSend(message: Record<string, unknown>): void {
  if (!isExtension) return;
  try { chrome.runtime.sendMessage(message).catch(() => {}); } catch { /* ignore */ }
}

/** Resolve a bundled asset (images under source/). */
export function assetUrl(path: string): string {
  if (isExtension && chrome.runtime?.getURL) return chrome.runtime.getURL(path);
  return `/${path}`;
}
