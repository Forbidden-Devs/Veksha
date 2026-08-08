import { useState } from "react";
import { useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";
import { LanguagePicker } from "../components/LanguagePicker";

const LANG_OPTIONS = LANGUAGES.filter((l) => l.code !== "auto");

function detectBrowserLang(): string {
  const raw = (navigator.languages?.[0] ?? navigator.language ?? "en").slice(0, 2).toLowerCase();
  return LANG_OPTIONS.some((l) => l.code === raw) ? raw : "en";
}

export function NativeLangScreen({
  initialLang,
  onContinue,
  onBack,
}: {
  initialLang?: string;
  onContinue: (lang: string) => Promise<void>;
  onBack: () => void;
}) {
  const t = useT();
  const [selected, setSelected] = useState<string>(() => initialLang ?? detectBrowserLang());
  const [loading, setLoading] = useState(false);

  async function handleContinue() {
    setLoading(true);
    await onContinue(selected);
    // component unmounts after this so no setLoading(false) needed
  }

  return (
    <LanguagePicker
      title={t.native_lang_title}
      searchLabel={t.settings_native_lang}
      emptyLabel={t.language_search_no_results}
      options={LANG_OPTIONS}
      selectedCodes={new Set([selected])}
      onSelect={setSelected}
      headerAction={
        <button className="onboarding-back" type="button" onClick={onBack} disabled={loading}>
          <span aria-hidden="true">←</span> {t.common_back}
        </button>
      }
      footer={
        <button
          className="btn btn-gradient btn-block"
          onClick={handleContinue}
          disabled={loading}
          type="button"
        >
          {loading ? t.app_loading : t.onboarding_continue}
        </button>
      }
    />
  );
}
