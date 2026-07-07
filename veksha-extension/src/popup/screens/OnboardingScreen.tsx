import { useState } from "react";
import { useT } from "../../shared/i18n";

interface Props {
  onComplete: (username: string) => Promise<void>;
}

export function OnboardingScreen({ onComplete }: Props) {
  const t = useT();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function validateUsername(name: string): string | null {
    const trimmed = name.trim();
    if (!trimmed) return t.onboarding_err_empty;
    if (trimmed.length > 64) return t.onboarding_err_long;
    // Any name in any language/script is allowed — no character restriction.
    return null;
  }

  async function handleContinue() {
    const err = validateUsername(value);
    if (err) { setError(err); return; }
    setError(null);
    setLoading(true);
    try {
      await onComplete(value.trim());
    } catch (e) {
      const msg = (e as Error).message;
      setError(msg === "username-taken" ? (t.onboarding_err_taken ?? "This name is already taken.") : msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="screen screen-onboarding">
      <div className="onboarding-card">
        <div className="logo-badge">Ve</div>
        <h1 className="onboarding-title">{t.onboarding_title}</h1>
        <p className="onboarding-subtitle">{t.onboarding_subtitle}</p>
        <input
          className="text-input"
          type="text"
          placeholder={t.onboarding_name_placeholder}
          autoComplete="off"
          maxLength={64}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleContinue()}
          autoFocus
        />
        <button className="btn btn-gradient" disabled={loading} onClick={handleContinue}>
          {loading ? t.onboarding_loading : t.onboarding_continue}
        </button>
        {error && <p className="onboarding-error">{error}</p>}
      </div>
    </section>
  );
}
