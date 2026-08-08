import { useState } from "react";
import { useI18n } from "../../shared/i18n";
import { UI_LOCALES } from "../../shared/i18n/locales";
import { LANGUAGES } from "../../shared/languages";
import { LanguagePicker } from "../components/LanguagePicker";

const UI_LANGUAGE_OPTIONS = UI_LOCALES.flatMap((code) => {
  const language = LANGUAGES.find((item) => item.code === code);
  return language ? [language] : [];
});

export function InterfaceLangScreen({
  initialLang,
  onContinue,
}: {
  initialLang: string;
  onContinue: (lang: string) => Promise<void>;
}) {
  const { t, previewLanguage } = useI18n();
  const [selected, setSelected] = useState(() => (
    UI_LOCALES.includes(initialLang) ? initialLang : "en"
  ));
  const [loading, setLoading] = useState(false);

  function handleContinue() {
    setLoading(true);
    void onContinue(selected).finally(() => setLoading(false));
  }

  function handleSelect(lang: string) {
    setSelected(lang);
    previewLanguage(lang);
  }

  return (
    <LanguagePicker
      title={t.settings_interface_language}
      searchLabel={t.settings_interface_language}
      emptyLabel={t.language_search_no_results}
      options={UI_LANGUAGE_OPTIONS}
      selectedCodes={new Set([selected])}
      onSelect={handleSelect}
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
