import { useState } from "react";
import { useT } from "../../shared/i18n";
import { LANGUAGES } from "../../shared/languages";
import { LanguagePicker } from "../components/LanguagePicker";

export function TargetLangScreen({
  nativeLang,
  initialLangs,
  onContinue,
  onBack,
}: {
  nativeLang: string;
  initialLangs?: string[];
  onContinue: (langs: string[]) => Promise<void>;
  onBack: () => void;
}) {
  const t = useT();
  const options = LANGUAGES.filter((l) => l.code !== "auto" && l.code !== nativeLang);
  const [selected, setSelected] = useState<string[]>(() => {
    return (initialLangs ?? []).filter((code) => options.some((l) => l.code === code));
  });
  const [loading, setLoading] = useState(false);

  function toggleLanguage(code: string) {
    setSelected((current) => current.includes(code)
      ? current.filter((selectedCode) => selectedCode !== code)
      : current.concat(code));
  }

  function handleContinue() {
    setLoading(true);
    void onContinue(selected).finally(() => setLoading(false));
  }

  return (
    <LanguagePicker
      title={t.target_lang_title}
      subtitle={t.target_lang_subtitle}
      searchLabel={t.settings_add_language}
      emptyLabel={t.language_search_no_results}
      options={options}
      selectedCodes={new Set(selected)}
      onSelect={toggleLanguage}
      headerAction={
        <button className="onboarding-back" type="button" onClick={onBack} disabled={loading}>
          <span aria-hidden="true">←</span> {t.common_back}
        </button>
      }
      footer={
        <button
          className="btn btn-gradient btn-block"
          onClick={handleContinue}
          disabled={loading || selected.length === 0}
          type="button"
        >
          {loading ? t.onboarding_loading : t.target_lang_start}
        </button>
      }
    />
  );
}
