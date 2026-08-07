import { createRoot } from "react-dom/client";
import { PracticePlannerWindow } from "../popup/overlays/PracticePlannerWindow";
import { I18nProvider, useT } from "../shared/i18n";
import { useStoredUsername } from "../shared/useStoredUsername";
import { initTheme } from "../shared/theme";
import { StandaloneMessage } from "../shared/StandaloneMessage";
import "../shared/palette.css";
import "../popup/styles/index.css";
import "../shared/standalone.css";

function TrainingApp() {
  const t = useT();
  const username = useStoredUsername();

  if (!username) {
    return <StandaloneMessage>{t.app_loading}</StandaloneMessage>;
  }

  return <PracticePlannerWindow username={username} onClose={() => window.close()} />;
}

const host = document.querySelector<HTMLElement>("#root");
if (!host) throw new Error("Training root is missing");
void initTheme().finally(() => {
  createRoot(host).render(<I18nProvider><TrainingApp /></I18nProvider>);
});
