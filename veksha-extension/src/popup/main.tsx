import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { I18nProvider } from "../shared/i18n";
import "../shared/palette.css";
import "./styles/index.css";
import { initTheme } from "../shared/theme";

import App from "./App";

const RootProviders = ({ children }: { children: ReactNode }) => (
  <StrictMode><I18nProvider>{children}</I18nProvider></StrictMode>
);

const popupHost = document.querySelector<HTMLElement>("#root");
if (!popupHost) throw new Error("Popup root is missing");
void initTheme().finally(() => {
  createRoot(popupHost).render(<RootProviders><App /></RootProviders>);
});
