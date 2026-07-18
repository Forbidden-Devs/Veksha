/**
 * Browser-neutral Google sign-in.
 *
 * Google always redirects to an HTTPS endpoint on the Veksha backend. The
 * extension opens that flow in a normal browser tab and polls the backend
 * with a high-entropy, single-use flow id. This avoids browser-specific
 * redirect schemes (chromiumapp.org, allizom.org, orion-oauth://, …).
 */
import { CONFIG } from "./config";

export interface GoogleLoginResult {
  username: string;
  token: string;
  display_name: string;
  created: boolean;
}

export interface GoogleLinkResult {
  ok: boolean;
  email: string;
}

interface FlowStart {
  flow_id: string;
  authorization_url: string;
  expires_in: number;
}

type FlowStatus<T> =
  | { status: "pending" }
  | { status: "complete"; result: T }
  | { status: "error"; error: string };

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function storedToken(): Promise<string> {
  const values = await chrome.storage.local.get(CONFIG.STORAGE_KEY_TOKEN);
  return String(values[CONFIG.STORAGE_KEY_TOKEN] ?? "");
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`google-flow HTTP ${response.status}: ${body.slice(0, 300)}`);
  }
  return response.json() as Promise<T>;
}

async function runGoogleFlow<T>(mode: "login" | "link"): Promise<T> {
  if (!CONFIG.GOOGLE_CLIENT_ID) throw new Error("google-not-configured");

  const token = mode === "link" ? await storedToken() : "";
  if (mode === "link" && !token) throw new Error("google-not-authenticated");
  const prefix = mode === "link" ? "/api/auth/google/link" : "/api/auth/google";
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const start = await requestJson<FlowStart>(`${CONFIG.BACKEND_URL}${prefix}/start`, {
    method: "POST",
    headers,
  });
  const tab = await chrome.tabs.create({ url: start.authorization_url, active: true });
  const deadline = Date.now() + Math.min(start.expires_in, 600) * 1000;

  try {
    while (Date.now() < deadline) {
      const status = await requestJson<FlowStatus<T>>(
        `${CONFIG.BACKEND_URL}${prefix}/status/${encodeURIComponent(start.flow_id)}`,
        { headers },
      );
      if (status.status === "complete") return status.result;
      if (status.status === "error") {
        throw new Error(status.error === "cancelled" ? "google-cancelled" : `google-${status.error}`);
      }

      // Treat a manually closed auth tab as cancellation. Check after polling
      // so a completed callback wins a close/poll race.
      if (tab.id != null) {
        try {
          await chrome.tabs.get(tab.id);
        } catch {
          throw new Error("google-cancelled");
        }
      }
      await sleep(800);
    }
    throw new Error("google-timeout");
  } finally {
    if (tab.id != null) await chrome.tabs.remove(tab.id).catch(() => {});
  }
}

export function googleSignIn(): Promise<GoogleLoginResult> {
  return runGoogleFlow<GoogleLoginResult>("login");
}

export function googleLinkAccount(): Promise<GoogleLinkResult> {
  return runGoogleFlow<GoogleLinkResult>("link");
}
