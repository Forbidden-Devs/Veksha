import { createRoot } from "react-dom/client";
import { GoalWindow, type GoalTarget } from "../popup/overlays/GoalWindow";
import { I18nProvider, useT } from "../shared/i18n";
import { useStoredUsername } from "../shared/useStoredUsername";
import { initTheme } from "../shared/theme";
import { StandaloneMessage } from "../shared/StandaloneMessage";
import "../shared/palette.css";
import "../popup/styles/index.css";
import "../shared/standalone.css";

function LessonApp() {
  const t = useT();
  const username = useStoredUsername();
  const params = new URLSearchParams(window.location.search);
  const goalId = params.get("goal") ?? "";
  const statement = params.get("statement") ?? "";
  const target: GoalTarget | null = goalId
    ? { goalId }
    : statement
      ? { statement }
      : null;

  if (!username) {
    return <StandaloneMessage>{t.app_loading}</StandaloneMessage>;
  }

  if (!target) {
    return <StandaloneMessage>{t.lesson_err_no_goal}</StandaloneMessage>;
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

const host = document.querySelector<HTMLElement>("#root");
if (!host) throw new Error("Lesson root is missing");
void initTheme().finally(() => {
  createRoot(host).render(<I18nProvider><LessonApp /></I18nProvider>);
});
