import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { I18nProvider } from "../../veksha-extension/src/shared/i18n";
import "../../veksha-extension/src/popup/popup.css";
import "../../veksha-extension/src/popup/theme.css";
import { initTheme } from "../../veksha-extension/src/shared/theme";

void initTheme();
import "./web.css";
import App from "../../veksha-extension/src/popup/App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>
);
