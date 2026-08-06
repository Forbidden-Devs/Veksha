import { useEffect, useMemo, useState } from "react";
import * as api from "../../shared/api";
import { useT } from "../../shared/i18n";

export type PaidFeature = "grammar_lens" | "immersion" | "dual_subtitles";
export type SubscriptionIntent = {
  mode: "new" | "manage" | "add";
  feature?: PaidFeature;
};

const FEATURE_ORDER: PaidFeature[] = ["grammar_lens", "immersion", "dual_subtitles"];

export function SubscriptionScreen({
  intent,
  onStatusChange,
}: {
  intent: SubscriptionIntent;
  onStatusChange: (status: api.BillingStatus) => void;
}) {
  const t = useT();
  const [features, setFeatures] = useState<api.BillingFeature[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [opened, setOpened] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([api.getBillingFeatures(), api.getBillingStatus()])
      .then(([catalog, status]) => {
        if (!alive) return;
        setFeatures([...catalog].sort(
          (a, b) => FEATURE_ORDER.indexOf(a.id) - FEATURE_ORDER.indexOf(b.id),
        ));
        onStatusChange(status);
        const active = new Set(status.features);
        if (intent.mode === "new") catalog.forEach((feature) => active.add(feature.id));
        if (intent.mode === "add" && intent.feature) active.add(intent.feature);
        setSelected(active);
      })
      .catch(() => { if (alive) setError(t.subscription_load_error); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [intent, onStatusChange, t.subscription_load_error]);

  const total = useMemo(
    () => features.reduce(
      (sum, feature) => sum + (selected.has(feature.id) ? feature.stars_monthly : 0),
      0,
    ),
    [features, selected],
  );

  function titleFor(feature: PaidFeature): string {
    if (feature === "grammar_lens") return t.pattern_workshop_title;
    if (feature === "immersion") return t.ci_meter_off;
    return t.settings_dual_subtitles;
  }

  function descriptionFor(feature: PaidFeature): string {
    if (feature === "grammar_lens") return t.subscription_grammar_desc;
    if (feature === "immersion") return t.reading_coach_guide_intro;
    return t.settings_dual_subtitles_desc;
  }

  function toggle(feature: string) {
    setOpened(false);
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(feature)) next.delete(feature);
      else next.add(feature);
      return next;
    });
  }

  async function continueToPayment() {
    setOpening(true);
    setError(null);
    try {
      const { url } = await api.createTelegramBillingLink([...selected]);
      window.open(url, "_blank", "noopener");
      setOpened(true);
    } catch {
      setError(t.settings_sub_err);
    } finally {
      setOpening(false);
    }
  }

  const intro = intent.mode === "manage"
    ? t.subscription_intro_manage
    : intent.mode === "add"
      ? t.subscription_intro_add
      : t.subscription_intro_new;

  return (
    <section className="screen subscription-screen">
      <div className="subscription-body">
        <div className="subscription-heading">
          <span className="subscription-heading-icon" aria-hidden="true">★</span>
          <div>
            <h1>{t.subscription_title}</h1>
            <p>{intro}</p>
          </div>
        </div>

        {loading && <p className="subscription-loading">{t.app_loading}</p>}

        {!loading && features.map((feature) => {
          const checked = selected.has(feature.id);
          return (
            <label className={`subscription-feature${checked ? " is-selected" : ""}`} key={feature.id}>
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(feature.id)}
              />
              <span className="subscription-check" aria-hidden="true">{checked ? "✓" : ""}</span>
              <span className="subscription-feature-copy">
                <strong>{titleFor(feature.id)}</strong>
                <small>{descriptionFor(feature.id)}</small>
              </span>
              <span className="subscription-feature-price">
                {feature.stars_monthly} ⭐
                <small>{t.subscription_monthly}</small>
              </span>
            </label>
          );
        })}

        {!loading && selected.size === 0 && (
          <p className="subscription-empty">{t.subscription_empty}</p>
        )}
        {opened && <p className="subscription-success">{t.subscription_opened}</p>}
        {error && <p className="onboarding-error">{error}</p>}
      </div>

      <footer className="subscription-footer">
        <div className="subscription-total">
          <span>{t.subscription_total}</span>
          <strong>{total} ⭐ <small>{t.subscription_monthly}</small></strong>
        </div>
        <button
          className="btn btn-gradient btn-block"
          type="button"
          disabled={loading || opening || selected.size === 0}
          onClick={continueToPayment}
        >
          {opening ? t.app_loading : t.subscription_continue}
        </button>
      </footer>
    </section>
  );
}
