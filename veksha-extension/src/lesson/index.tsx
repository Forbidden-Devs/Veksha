import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { LessonWindow } from "../popup/overlays/LessonWindow";
import { I18nProvider, useT } from "../shared/i18n";
import { CONFIG } from "../shared/config";
import "../shared/palette.css";
import "../popup/popup.css";
import "../popup/theme.css";
import { initTheme } from "../shared/theme";

void initTheme();
import "../shared/standalone.css";

function LessonApp() {
  const t = useT();
  const [username, setUsername] = useState<string | null>(null);
  const topicName = new URLSearchParams(window.location.search).get("topic") ?? "";

  useEffect(() => {
    chrome.storage.local.get([CONFIG.STORAGE_KEY_USERNAME], (result) => {
      setUsername((result[CONFIG.STORAGE_KEY_USERNAME] as string) ?? null);
    });
  }, []);

  if (!username) {
    return (
      <div style={{ padding: 20, fontFamily: "sans-serif", color: "#888" }}>
        {t.app_loading}
      </div>
    );
  }

  if (!topicName) {
    return (
      <div style={{ padding: 20, fontFamily: "sans-serif", color: "#888" }}>
        {t.lesson_err_no_topic}
      </div>
    );
  }

  return <LessonWindow username={username} topicName={topicName} onClose={() => window.close()} />;
}

createRoot(document.getElementById("root")!).render(
  <I18nProvider>
    <LessonApp />
  </I18nProvider>
);
