import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { GoalWindow, type GoalTarget } from "../popup/overlays/GoalWindow";
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
  const params = new URLSearchParams(window.location.search);
  const goalId = params.get("goal") ?? "";
  const statement = params.get("statement") ?? "";
  const target: GoalTarget | null = goalId
    ? { goalId }
    : statement
      ? { statement }
      : null;

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

  if (!target) {
    return (
      <div style={{ padding: 20, fontFamily: "sans-serif", color: "#888" }}>
        {t.lesson_err_no_goal}
      </div>
    );
  }

  return (
    <GoalWindow
      username={username}
      target={target}
      title={statement || undefined}
      onClose={() => window.close()}
    />
  );
}

createRoot(document.getElementById("root")!).render(
  <I18nProvider>
    <LessonApp />
  </I18nProvider>
);
