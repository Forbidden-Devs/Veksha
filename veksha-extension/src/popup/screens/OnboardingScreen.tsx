import { useState } from "react";
import { GoogleMark } from "../../shared/GoogleMark";
import { useT } from "../../shared/i18n";

interface Props {
  initialName?: string;
  onComplete: (name: string) => Promise<void>;
  onGoogle?: () => Promise<void>;
  onBack: () => void;
}

export function OnboardingScreen({ initialName = "", onComplete, onGoogle, onBack }: Props) {
  const t = useT();
  const [name, setName] = useState(initialName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    const value = name.trim();
    if (!value) return setError(t.onboarding_err_empty);
    if (value.length > 64) return setError(t.onboarding_err_long);
    setBusy(true);
    setError("");
    try { await onComplete(value); }
    catch (reason) { setError((reason as Error).message); setBusy(false); }
  }

  async function useGoogle(): Promise<void> {
    if (!onGoogle) return;
    setBusy(true);
    setError("");
    try { await onGoogle(); }
    catch (reason) {
      if ((reason as Error).message !== "google-cancelled") setError(t.onboarding_google_err);
      setBusy(false);
    }
  }

  return (
    <section className="setup-surface" aria-labelledby="setup-welcome-title">
      <button className="setup-back" type="button" onClick={onBack} disabled={busy}>← {t.common_back}</button>
      <form className="setup-card" onSubmit={(event) => void submit(event)}>
        <div className="setup-mark" aria-hidden="true">Ve</div>
        <p className="setup-kicker">VEKSHA</p>
        <h1 id="setup-welcome-title">{t.onboarding_title}</h1>
        <p>{t.onboarding_subtitle}</p>
        <label className="setup-field">
          <span>{t.settings_display_name}</span>
          <input value={name} onChange={(event) => setName(event.target.value)} maxLength={64} autoComplete="name" autoFocus placeholder={t.onboarding_name_placeholder} />
        </label>
        {error && <p className="setup-error" role="alert">{error}</p>}
        <button className="setup-primary" type="submit" disabled={busy}>{busy ? t.onboarding_loading : t.onboarding_continue}</button>
        {onGoogle && <button className="setup-google" type="button" onClick={() => void useGoogle()} disabled={busy}><GoogleMark />{t.onboarding_google}</button>}
      </form>
    </section>
  );
}
