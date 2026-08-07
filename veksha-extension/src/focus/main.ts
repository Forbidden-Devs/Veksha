import { CONFIG } from "../shared/config";
import { focusSiteForUrl, type FocusSession } from "../shared/focusSession";

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

async function load(): Promise<void> {
  const values = await chrome.storage.local.get([CONFIG.STORAGE_KEY_FOCUS_SESSION]);
  session = (values[CONFIG.STORAGE_KEY_FOCUS_SESSION] as FocusSession | undefined) ?? null;
  if (!session || session.endsAt <= Date.now()) {
    await chrome.storage.local.remove([CONFIG.STORAGE_KEY_FOCUS_SESSION]);
    if (target) location.replace(target);
    return;
  }
  intention.textContent = session.intention || "Your study session is still active";
  renderRemaining();
  window.setInterval(renderRemaining, 1000);
  const timer = window.setInterval(() => {
    seconds -= 1;
    pause.textContent = seconds > 0 ? `Pause for ${seconds} seconds` : "Choose deliberately";
    if (seconds <= 0) {
      access.disabled = false;
      window.clearInterval(timer);
    }
  }, 1000);
  pause.textContent = `Pause for ${seconds} seconds`;
}

function renderRemaining(): void {
  if (!session) return;
  const minutes = Math.max(0, Math.ceil((session.endsAt - Date.now()) / 60000));
  remaining.textContent = `You intended to study for ${minutes} more minute${minutes === 1 ? "" : "s"}.`;
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
