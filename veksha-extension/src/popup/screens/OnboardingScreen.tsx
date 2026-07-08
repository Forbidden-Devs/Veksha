import { useState } from "react";
import { GoogleMark } from "../../shared/GoogleMark";
import { useT } from "../../shared/i18n";

interface Props {
  onComplete: (username: string) => Promise<void>;
  /** Google sign-in; omitted when CONFIG.GOOGLE_CLIENT_ID is not set. */
  onGoogle?: () => Promise<void>;
}

export function OnboardingScreen({ onComplete, onGoogle }: Props) {
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
      // Display names don't collide (the account id is generated server-side),
      // so any failure here is a real error worth showing as-is.
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogle() {
    if (!onGoogle) return;
    setError(null);
    setLoading(true);
    try {
      await onGoogle();
    } catch (e) {
      // Closing the Google window is not an error worth showing.
      if ((e as Error).message !== "google-cancelled") setError(t.onboarding_google_err);
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
        {onGoogle && (
          <>
            <div className="onboarding-divider">{t.onboarding_or}</div>
            <button className="btn btn-google" disabled={loading} onClick={handleGoogle}>
              <GoogleMark />
              {t.onboarding_google}
            </button>
          </>
        )}
        {error && <p className="onboarding-error">{error}</p>}
      </div>
    </section>
  );
}
