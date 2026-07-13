/**
 * offscreen.ts — Chrome-only host for the capture controller.
 *
 * Chrome MV3 backgrounds are service workers without DOM, so the background
 * creates this offscreen document and drives it via runtime messages. On
 * Firefox the background event page runs shared/capture directly and this
 * document is never created.
 */
import { createCaptureController } from "../shared/capture";

const capture = createCaptureController((message) => {
  chrome.runtime.sendMessage({ target: "background", ...message }).catch(() => {});
});

chrome.runtime.onMessage.addListener((msg: Record<string, unknown>, _sender, sendResponse) => {
  if (msg.target !== "offscreen") return false;

  if (msg.type === "OCR_REGION") {
    void capture.handleOcrRegion(msg);
    sendResponse({ ok: true });
    return false;
  }

  return false;
});
