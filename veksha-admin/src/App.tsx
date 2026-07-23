import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AdminApiError, adminApi, type AdminOverview, type PromoDraft } from "./api";

const FEATURE_NAMES: Record<string, string> = {
  grammar_lens: "CI-метр и Grammar Lens",
  immersion: "Погружение в страницу",
  dual_subtitles: "Двойные субтитры",
};

const emptyPromo: PromoDraft = {
  code: "",
  days: 30,
  max_redemptions: 1,
  note: "",
  features: [],
};

function readableError(error: unknown): string {
  if (error instanceof AdminApiError && error.status === 401) return "Неверный секрет администратора";
  return error instanceof Error ? error.message : "Неизвестная ошибка";
}

export default function App() {
  const [secret, setSecret] = useState(() => sessionStorage.getItem("veksha-admin-secret") || "");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [promo, setPromo] = useState<PromoDraft>(emptyPromo);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async (authSecret: string) => {
    setBusy(true);
    setMessage("");
    try {
      const data = await adminApi.overview(authSecret);
      sessionStorage.setItem("veksha-admin-secret", authSecret);
      setOverview(data);
      setPrices(Object.fromEntries(data.features.map((item) => [item.feature, item.stars_monthly])));
    } catch (error) {
      sessionStorage.removeItem("veksha-admin-secret");
      setOverview(null);
      setMessage(readableError(error));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { if (secret) void load(secret); }, []); // restore this tab's session once

  const monthlyTotal = useMemo(
    () => Object.values(prices).reduce((sum, price) => sum + (Number(price) || 0), 0),
    [prices],
  );

  async function signIn(event: FormEvent) {
    event.preventDefault();
    if (secret.trim()) await load(secret.trim());
  }

  async function savePrice(feature: string) {
    const value = Number(prices[feature]);
    if (!Number.isInteger(value) || value < 1) {
      setMessage("Цена должна быть целым числом больше нуля");
      return;
    }
    setBusy(true);
    try {
      await adminApi.setPrice(secret, feature, value);
      setMessage("Цена сохранена. Новые формы оплаты будут использовать её сразу.");
      await load(secret);
    } catch (error) {
      setMessage(readableError(error));
      setBusy(false);
    }
  }

  async function createPromo(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await adminApi.createPromo(secret, promo);
      setPromo(emptyPromo);
      setMessage("Промокод создан");
      await load(secret);
    } catch (error) {
      setMessage(readableError(error));
      setBusy(false);
    }
  }

  function signOut() {
    sessionStorage.removeItem("veksha-admin-secret");
    setSecret("");
    setOverview(null);
    setMessage("");
  }

  if (!overview) {
    return <main className="login-shell">
      <form className="login-card" onSubmit={signIn}>
        <div className="brand-mark">V</div>
        <p className="eyebrow">VEKSHA CONTROL ROOM</p>
        <h1>Панель управления</h1>
        <p className="muted">Введите административный секрет. Он сохраняется только до закрытия вкладки.</p>
        <label>Секрет<input autoFocus type="password" value={secret} onChange={(e) => setSecret(e.target.value)} /></label>
        {message && <p className="notice error" role="alert">{message}</p>}
        <button className="primary" disabled={busy || !secret.trim()}>{busy ? "Проверяем…" : "Войти"}</button>
      </form>
    </main>;
  }

  return <main className="app-shell">
    <header>
      <div><p className="eyebrow">VEKSHA ADMIN</p><h1>Монетизация</h1></div>
      <div className="header-actions"><button className="ghost" onClick={() => void load(secret)}>Обновить</button><button className="ghost" onClick={signOut}>Выйти</button></div>
    </header>
    {message && <div className="notice" role="status">{message}<button aria-label="Закрыть" onClick={() => setMessage("")}>×</button></div>}

    <section>
      <div className="section-heading"><div><p className="eyebrow">КАТАЛОГ</p><h2>Стоимость функций</h2></div><strong>{monthlyTotal} ⭐ / месяц за всё</strong></div>
      <div className="price-grid">
        {overview.features.map((item) => <article className="price-card" key={item.feature}>
          <span className="feature-code">{item.feature}</span>
          <h3>{FEATURE_NAMES[item.feature] || item.feature}</h3>
          <label className="price-input"><input type="number" min="1" step="1" value={prices[item.feature] ?? item.stars_monthly} onChange={(e) => setPrices({ ...prices, [item.feature]: Number(e.target.value) })} /><span>⭐ / месяц</span></label>
          <button disabled={busy || prices[item.feature] === item.stars_monthly} onClick={() => void savePrice(item.feature)}>Сохранить цену</button>
        </article>)}
      </div>
    </section>

    <section className="promo-layout">
      <form className="panel" onSubmit={createPromo}>
        <p className="eyebrow">НОВЫЙ ПРОМОКОД</p><h2>Создать доступ</h2>
        <div className="form-grid">
          <label>Код<input required placeholder="WELCOME30" value={promo.code} onChange={(e) => setPromo({ ...promo, code: e.target.value.toUpperCase() })} /></label>
          <label>Дней<input required type="number" min="1" value={promo.days} onChange={(e) => setPromo({ ...promo, days: Number(e.target.value) })} /></label>
          <label>Использований<input required type="number" min="1" value={promo.max_redemptions} onChange={(e) => setPromo({ ...promo, max_redemptions: Number(e.target.value) })} /></label>
          <label>Заметка<input placeholder="Для партнёров" value={promo.note} onChange={(e) => setPromo({ ...promo, note: e.target.value })} /></label>
        </div>
        <fieldset><legend>Доступные функции</legend><p className="hint">Если ничего не выбрано, промокод откроет все платные функции.</p>
          {overview.features.map((item) => <label className="check" key={item.feature}><input type="checkbox" checked={promo.features.includes(item.feature)} onChange={(e) => setPromo({ ...promo, features: e.target.checked ? [...promo.features, item.feature] : promo.features.filter((id) => id !== item.feature) })} /><span>{FEATURE_NAMES[item.feature] || item.feature}</span></label>)}
        </fieldset>
        <button className="primary" disabled={busy || !promo.code.trim()}>Создать промокод</button>
      </form>

      <div className="panel promo-list"><div className="section-heading"><div><p className="eyebrow">ИСТОРИЯ</p><h2>Последние промокоды</h2></div><span>{overview.promos.length}</span></div>
        {overview.promos.length === 0 ? <p className="empty">Промокодов пока нет</p> : <div className="table-wrap"><table><thead><tr><th>Код</th><th>Доступ</th><th>Срок</th><th>Использовано</th></tr></thead><tbody>
          {overview.promos.map((item) => <tr key={item.code}><td><code>{item.code}</code><small>{item.note}</small></td><td>{item.features.length ? item.features.map((id) => FEATURE_NAMES[id] || id).join(", ") : "Все функции"}</td><td>{item.days} дн.</td><td>{item.redemptions} / {item.max_redemptions}</td></tr>)}
        </tbody></table></div>}
      </div>
    </section>
  </main>;
}
