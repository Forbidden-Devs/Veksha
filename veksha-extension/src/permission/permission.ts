async function requestPermission() {
  const button = document.querySelector<HTMLButtonElement>("#allow-microphone");
  if (button) {
    button.disabled = true;
    button.textContent = "Requesting access…";
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(track => track.stop());
    await chrome.runtime.sendMessage({ type: "VOICE_PERMISSION_GRANTED" });
  } catch (err) {
    await chrome.runtime.sendMessage({
      type: "VOICE_PERMISSION_DENIED",
      error: err instanceof Error ? err.name : String(err),
    });
  } finally {
    window.setTimeout(() => window.close(), 100);
  }
}

document.querySelector("#allow-microphone")?.addEventListener("click", () => {
  void requestPermission();
}, { once: true });
