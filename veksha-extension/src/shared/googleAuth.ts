/**
 * googleAuth.ts — Google sign-in for the extension popup.
 *
 * Runs the OAuth implicit flow (response_type=id_token) inside the browser's
 * extension-auth window via chrome.identity.launchWebAuthFlow — works in both
 * Chrome (…chromiumapp.org redirect) and Firefox (…allizom.org redirect).
 * The returned ID token is sent to POST /api/auth/google, which verifies it
 * and issues our own bearer token.
 *
 * Setup: register chrome.identity.getRedirectURL() as an authorized redirect
 * URI of the Google OAuth client (see veksha-extension/README.md).
 */
import { CONFIG } from "./config";

const GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";

function decodeJwtPayload(idToken: string): Record<string, unknown> {
  const base64 = idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(atob(base64)) as Record<string, unknown>;
}

/** Interactive Google sign-in; resolves with a nonce-checked Google ID token.
 *  Throws Error("google-cancelled") when the user closes the auth window. */
export async function googleSignIn(): Promise<string> {
  if (!CONFIG.GOOGLE_CLIENT_ID) throw new Error("google-not-configured");

  const redirectUri = chrome.identity.getRedirectURL();
  const nonce = crypto.randomUUID().replace(/-/g, "");
  const params = new URLSearchParams({
    client_id: CONFIG.GOOGLE_CLIENT_ID,
    response_type: "id_token",
    redirect_uri: redirectUri,
    scope: "openid email profile",
    nonce,
    prompt: "select_account",
  });

  let resultUrl: string | undefined;
  try {
    resultUrl = await chrome.identity.launchWebAuthFlow({
      url: `${GOOGLE_AUTH_URL}?${params.toString()}`,
      interactive: true,
    });
  } catch {
    // Both browsers reject when the user closes the window.
    throw new Error("google-cancelled");
  }
  if (!resultUrl) throw new Error("google-cancelled");

  const fragment = new URL(resultUrl).hash.replace(/^#/, "");
  const idToken = new URLSearchParams(fragment).get("id_token");
  if (!idToken) throw new Error("google-no-token");

  // The nonce must round-trip into the token — guards against a response
  // injected into the auth window.
  if (decodeJwtPayload(idToken).nonce !== nonce) throw new Error("google-bad-nonce");
  return idToken;
}
