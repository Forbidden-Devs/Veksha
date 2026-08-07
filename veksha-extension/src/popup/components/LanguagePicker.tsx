import { useMemo, useState, type ReactNode } from "react";
import { useI18n } from "../../shared/i18n";
import { getLanguageName, type Language } from "../../shared/languages";

interface LanguagePickerProps {
  title: string;
  subtitle: string;
  searchLabel: string;
  emptyLabel: string;
  options: Language[];
  selectedCodes: ReadonlySet<string>;
  onSelect: (code: string) => void;
  headerAction?: ReactNode;
  footer: ReactNode;
}

export function LanguagePicker(props: LanguagePickerProps) {
  const { lang } = useI18n();
  const [query, setQuery] = useState("");
  const matches = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    const localized = props.options.map((language) => ({
      ...language,
      localizedName: getLanguageName(language.code, lang),
    }));
    if (!needle) return localized;
    return localized.filter(({ code, name, localizedName }) => (
      code.includes(needle)
      || name.toLocaleLowerCase().includes(needle)
      || localizedName.toLocaleLowerCase().includes(needle)
    ));
  }, [lang, props.options, query]);

  return (
    <section className="screen screen-lang-pick">
      <header className="lang-pick-header">
        {props.headerAction}
        <div className="logo-badge" aria-hidden="true">Ve</div>
        <h1 className="lang-pick-title">{props.title}</h1>
        <p className="lang-pick-subtitle">{props.subtitle}</p>
      </header>
      <input
        className="text-input lang-pick-search"
        type="search"
        value={query}
        aria-label={props.searchLabel}
        placeholder={props.searchLabel}
        onChange={({ currentTarget }) => setQuery(currentTarget.value)}
      />
      <div className="lang-pick-grid">
        {matches.map(({ code, localizedName }) => {
          const chosen = props.selectedCodes.has(code);
          return (
            <button
              key={code}
              type="button"
              className={`lang-card${chosen ? " lang-card--selected" : ""}`}
              aria-pressed={chosen}
              onClick={() => props.onSelect(code)}
            >
              <span className="lang-card-name">{localizedName}</span>
            </button>
          );
        })}
        {!matches.length && <p className="lang-pick-empty">{props.emptyLabel}</p>}
      </div>
      <footer className="lang-pick-footer">{props.footer}</footer>
    </section>
  );
}
