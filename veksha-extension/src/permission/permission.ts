async function requestPermission() {
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
    window.close();
  }
}

void requestPermission();
