import "../shared/palette.css";
import "./style.css";
import { getSettings, translateImageRegion } from "../shared/api";
import { CONFIG } from "../shared/config";
import { loadOrGenerateTranslation } from "../shared/i18n";

type Point = { x: number; y: number };
type Box = { left: number; top: number; width: number; height: number };

const image = document.querySelector<HTMLImageElement>("#capture-image")!;
const wrap = document.querySelector<HTMLElement>("#image-wrap")!;
const selection = document.querySelector<HTMLElement>("#selection")!;
const translateButton = document.querySelector<HTMLButtonElement>("#translate")!;
const resetButton = document.querySelector<HTMLButtonElement>("#reset")!;
const copyButton = document.querySelector<HTMLButtonElement>("#copy")!;
const resultPanel = document.querySelector<HTMLElement>("#result")!;
const status = document.querySelector<HTMLElement>("#status")!;
let start: Point | null = null;
let box: Box | null = null;
let strings: Record<string, string> = {};
let sourceLang = "auto";
let targetLang = "en";

function t(key: string, fallback: string): string { return strings[key] ?? fallback; }
function point(event: PointerEvent): Point {
  const rect = image.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(rect.width, event.clientX - rect.left)),
    y: Math.max(0, Math.min(rect.height, event.clientY - rect.top)),
  };
}
function draw(a: Point, b: Point): void {
  box = {
    left: Math.min(a.x, b.x), top: Math.min(a.y, b.y),
    width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y),
  };
  Object.assign(selection.style, {
    left: `${image.offsetLeft + box.left}px`, top: `${image.offsetTop + box.top}px`,
    width: `${box.width}px`, height: `${box.height}px`,
  });
  selection.hidden = false;
  translateButton.disabled = box.width < 20 || box.height < 12;
}

wrap.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || resultPanel.hidden === false) return;
  start = point(event);
  wrap.setPointerCapture(event.pointerId);
  draw(start, start);
});
wrap.addEventListener("pointermove", (event) => { if (start) draw(start, point(event)); });
wrap.addEventListener("pointerup", (event) => {
  if (start) draw(start, point(event));
  start = null;
});

function crop(): string {
  if (!box) throw new Error("no selection");
  const rect = image.getBoundingClientRect();
  const scaleX = image.naturalWidth / rect.width;
  const scaleY = image.naturalHeight / rect.height;
  const sourceWidth = Math.max(1, Math.round(box.width * scaleX));
  const sourceHeight = Math.max(1, Math.round(box.height * scaleY));
  const boost = Math.min(2, Math.max(1, 900 / sourceWidth));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(sourceWidth * boost);
  canvas.height = Math.round(sourceHeight * boost);
  const context = canvas.getContext("2d", { alpha: false });
  if (!context) throw new Error("canvas unavailable");
  context.imageSmoothingEnabled = false;
  context.drawImage(
    image, Math.round(box.left * scaleX), Math.round(box.top * scaleY), sourceWidth, sourceHeight,
    0, 0, canvas.width, canvas.height,
  );
  return canvas.toDataURL("image/png");
}

translateButton.addEventListener("click", async () => {
  translateButton.disabled = true;
  status.textContent = t("content_translating", "Translating…");
  try {
    const response = await translateImageRegion(crop(), sourceLang, targetLang);
    document.querySelector("#recognized")!.textContent = response.recognized_text;
    document.querySelector("#translation")!.textContent = response.translation;
    document.querySelector("#provider")!.textContent = response.provider === "google" ? "Cloud OCR" : "Vision fallback";
    resultPanel.hidden = false;
    resetButton.hidden = false;
    status.textContent = "";
  } catch {
    status.textContent = t("pdf_no_text", "No readable text was found in this area.");
    translateButton.disabled = false;
  }
});

copyButton.addEventListener("click", async () => {
  const translation = document.querySelector("#translation")!.textContent ?? "";
  if (!translation) return;
  await navigator.clipboard.writeText(translation);
  copyButton.textContent = t("ocr_translation_copied", "Copied");
  window.setTimeout(() => {
    copyButton.textContent = t("ocr_copy_translation", "Copy translation");
  }, 1400);
});

resetButton.addEventListener("click", () => {
  resultPanel.hidden = true;
  resetButton.hidden = true;
  selection.hidden = true;
  box = null;
  translateButton.disabled = true;
});

async function initialize(): Promise<void> {
  const stored = await chrome.storage.local.get([
    CONFIG.STORAGE_KEY_USERNAME, CONFIG.STORAGE_KEY_NATIVE_LANG, CONFIG.STORAGE_KEY_LANG_PAIR, "vk_theme",
  ]);
  document.documentElement.dataset.vekshaTheme = String(stored.vk_theme ?? "light");
  const nativeLang = String(stored[CONFIG.STORAGE_KEY_NATIVE_LANG] ?? "en");
  strings = await loadOrGenerateTranslation(nativeLang) as unknown as Record<string, string>;
  targetLang = nativeLang;
  const username = String(stored[CONFIG.STORAGE_KEY_USERNAME] ?? "");
  if (username) {
    try {
      const settings = await getSettings(username);
      sourceLang = "auto";
      targetLang = settings.native_lang || nativeLang;
    } catch {}
  }
  document.querySelector("#capture-title")!.textContent = t("pdf_translate_region", "Translate area");
  document.querySelector("#capture-hint")!.textContent = t("ocr_capture_hint", "Drag across the text you want to translate.");
  document.querySelector("#source-label")!.textContent = t("ocr_recognized_text", "Recognized text");
  document.querySelector("#translation-label")!.textContent = t("translator_result_label", "Translation");
  translateButton.textContent = t("ocr_translate_selection", "Translate selection");
  resetButton.textContent = t("ocr_choose_again", "Choose again");
  copyButton.textContent = t("ocr_copy_translation", "Copy translation");

  const token = location.hash.slice(1);
  const response = await chrome.runtime.sendMessage({ type: "VEKSHA_GET_REGION_CAPTURE", token }) as
    { ok?: boolean; image?: string };
  if (!response?.ok || !response.image) throw new Error("capture expired");
  image.src = response.image;
}

void initialize().catch(() => {
  status.textContent = "The captured page is no longer available. Start again from the context menu.";
});
