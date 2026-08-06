import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { I18nProvider } from "../shared/i18n";
import "../shared/palette.css";
import "./styles/index.css";
import { initTheme } from "../shared/theme";

void initTheme();
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>
);
