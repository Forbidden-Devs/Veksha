import { CONFIG } from "../shared/config";
import { focusSiteForUrl, type FocusSession } from "../shared/focusSession";
import { loadStaticCatalog, UI_LOCALE_STORAGE_KEY } from "../shared/i18n";
import type { Strings } from "../shared/i18n/strings";

const params = new URLSearchParams(location.search);
const rawTarget = params.get("target") ?? "";
const target = focusSiteForUrl(rawTarget) ? rawTarget : "";
const site = params.get("site") ?? "";
const intention = document.getElementById("intention")!;
const remaining = document.getElementById("remaining")!;
const pause = document.getElementById("pause")!;
const access = document.getElementById("access") as HTMLButtonElement;
const returnButton = document.getElementById("return") as HTMLButtonElement;
const endButton = document.getElementById("end") as HTMLButtonElement;

let session: FocusSession | null = null;
let seconds = 7;
let t: Strings;

async function load(): Promise<void> {
  const values = await chrome.storage.local.get([CONFIG.STORAGE_KEY_FOCUS_SESSION, UI_LOCALE_STORAGE_KEY]);
  t = await loadStaticCatalog(String(values[UI_LOCALE_STORAGE_KEY] ?? navigator.language.slice(0, 2)));
  returnButton.textContent = t.focus_return_to_study;
  access.textContent = t.focus_access_site;
  endButton.textContent = t.focus_session_end;
  session = (values[CONFIG.STORAGE_KEY_FOCUS_SESSION] as FocusSession | undefined) ?? null;
  if (!session || session.endsAt <= Date.now()) {
    await chrome.storage.local.remove([CONFIG.STORAGE_KEY_FOCUS_SESSION]);
    if (target) location.replace(target);
    return;
  }
  intention.textContent = session.intention || t.focus_session_title;
  renderRemaining();
  window.setInterval(renderRemaining, 1000);
  const timer = window.setInterval(() => {
    seconds -= 1;
    pause.textContent = seconds > 0
      ? t.focus_pause_seconds.replace("{n}", String(seconds))
      : t.focus_choose_deliberately;
    if (seconds <= 0) {
      access.disabled = false;
      window.clearInterval(timer);
    }
  }, 1000);
  pause.textContent = t.focus_pause_seconds.replace("{n}", String(seconds));
}

function renderRemaining(): void {
  if (!session) return;
  const minutes = Math.max(0, Math.ceil((session.endsAt - Date.now()) / 60000));
  remaining.textContent = t.focus_session_active.replace("{n}", String(minutes));
}

returnButton.addEventListener("click", () => history.length > 1 ? history.back() : window.close());
access.addEventListener("click", async () => {
  if (!session || !site || !target) return;
  session = { ...session, graceUntil: { ...session.graceUntil, [site]: Date.now() + 10 * 60 * 1000 } };
  await chrome.storage.local.set({ [CONFIG.STORAGE_KEY_FOCUS_SESSION]: session });
  location.replace(target);
});
endButton.addEventListener("click", async () => {
  await chrome.storage.local.remove([CONFIG.STORAGE_KEY_FOCUS_SESSION]);
  if (target) location.replace(target);
});

void load();
