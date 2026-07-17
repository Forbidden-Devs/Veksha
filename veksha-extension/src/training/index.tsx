import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { TrainingWindow } from "../popup/overlays/TrainingWindow";
import { I18nProvider, useT } from "../shared/i18n";
import { CONFIG } from "../shared/config";
import "../shared/palette.css";
import "../popup/popup.css";
import "../popup/theme.css";
import { initTheme } from "../shared/theme";

void initTheme();
import "../shared/standalone.css";

function TrainingApp() {
  const t = useT();
  const [username, setUsername] = useState<string | null>(null);

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

  return <TrainingWindow username={username} onClose={() => window.close()} />;
}

createRoot(document.getElementById("root")!).render(
  <I18nProvider>
    <TrainingApp />
  </I18nProvider>
);
