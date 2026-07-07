import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { I18nProvider } from "../shared/i18n";
import "./popup.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>
);
