import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { I18nProvider } from "../../veksha-extension/src/shared/i18n";
import "../../veksha-extension/src/popup/popup.css";
import "./web.css";
import App from "../../veksha-extension/src/popup/App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>
);
