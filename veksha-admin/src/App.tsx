import { FormEvent, useCallback, useMemo, useState } from "react";
import { AdminApiError, adminApi, type AdminOverview, type DatabaseQueryResult, type PromoDraft } from "./api";

const FEATURE_NAMES: Record<string, string> = {
  grammar_lens: "CI-метр и Grammar Lens",
  immersion: "Погружение в страницу",
  dual_subtitles: "Двойные субтитры",
};

const OPERATION_NAMES: Record<string, string> = {
  generate_tutor_task: "Задание тренировки",
  check_synonym_appropriate: "Проверка синонима",
  get_reverse_translations: "Обратный перевод",
  check_training_answer: "Проверка ответа",
  translate_selection: "Перевод выделения",
  explain_selection: "Объяснение выделения",
  extract_metadata: "Метаданные текста",
  ci_meter_classify: "Оценка сложности",
  sentence_mining: "Примеры для слова",
  suggest_block_names: "Темы урока",
  generate_block_content: "Содержание урока",
  review_block_content: "Проверка урока",
  generate_lesson_question: "Вопрос урока",
  check_lesson_answer: "Проверка ответа урока",
  grammar_lens_analyze: "Grammar Lens",
  dualsub: "Перевод субтитров",
  dualsub_batch: "Пакет субтитров",
  immersion_analyze: "Погружение",
};

const emptyPromo: PromoDraft = {
  code: "",
  days: 30,
  max_redemptions: 1,
  note: "",
  features: [],
};

const DEFAULT_DATABASE_QUERY = `SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name`;

function readableError(error: unknown): string {
  if (error instanceof AdminApiError && error.status === 401) return "Неверный секрет администратора";
  return error instanceof Error ? error.message : "Неизвестная ошибка";
}

const numberFormat = new Intl.NumberFormat("ru-RU");

function formatNumber(value: number): string {
  return numberFormat.format(value);
}

function formatDate(timestamp: number): string {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" })
    .format(new Date(timestamp * 1000));
}

function formatCell(value: unknown): string {
  if (value === null) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function App() {
  const [secret, setSecret] = useState("");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [promo, setPromo] = useState<PromoDraft>(emptyPromo);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [databaseSecret, setDatabaseSecret] = useState("");
  const [databaseSql, setDatabaseSql] = useState(DEFAULT_DATABASE_QUERY);
  const [databaseResult, setDatabaseResult] = useState<DatabaseQueryResult | null>(null);
  const [databaseBusy, setDatabaseBusy] = useState(false);
  const [databaseError, setDatabaseError] = useState("");

  const load = useCallback(async (authSecret: string) => {
    setBusy(true);
    setMessage("");
    try {
      const data = await adminApi.overview(authSecret);
      setOverview(data);
      setPrices(Object.fromEntries(data.features.map((item) => [item.feature, item.stars_monthly])));
    } catch (error) {
      setOverview(null);
      setMessage(readableError(error));
    } finally {
      setBusy(false);
    }
  }, []);

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

  async function queryDatabase(event: FormEvent) {
    event.preventDefault();
    if (!databaseSecret.trim() || !databaseSql.trim()) return;
    setDatabaseBusy(true);
    setDatabaseError("");
    try {
      setDatabaseResult(await adminApi.databaseQuery(secret, databaseSecret.trim(), databaseSql));
    } catch (error) {
      setDatabaseResult(null);
      if (error instanceof AdminApiError && error.status === 401) {
        setDatabaseError("Неверный отдельный секрет базы данных");
      } else {
        setDatabaseError(readableError(error));
      }
    } finally {
      setDatabaseBusy(false);
    }
  }

  function signOut() {
    setSecret("");
    setOverview(null);
    setMessage("");
    setDatabaseSecret("");
    setDatabaseResult(null);
    setDatabaseError("");
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
      <div><p className="eyebrow">VEKSHA ADMIN</p><h1>Панель управления</h1></div>
      <div className="header-actions"><button className="ghost" onClick={() => void load(secret)}>Обновить</button><button className="ghost" onClick={signOut}>Выйти</button></div>
    </header>
    {message && <div className="notice" role="status">{message}<button aria-label="Закрыть" onClick={() => setMessage("")}>×</button></div>}

    <section>
      <div className="section-heading"><div><p className="eyebrow">AI USAGE</p><h2>Использование AI</h2></div><span className="period-label">Последние {overview.ai_usage.period_days} дней</span></div>
      <div className="metric-grid">
        <article className="metric-card"><span>Токенов</span><strong>{formatNumber(overview.ai_usage.period.total_tokens)}</strong><small>за период</small></article>
        <article className="metric-card"><span>AI-запросов</span><strong>{formatNumber(overview.ai_usage.period.requests)}</strong><small>успешных вызовов</small></article>
        <article className="metric-card"><span>Активных пользователей</span><strong>{formatNumber(overview.ai_usage.period.active_users)}</strong><small>за период</small></article>
        <article className="metric-card"><span>За всё время</span><strong>{formatNumber(overview.ai_usage.all_time.total_tokens)}</strong><small>{formatNumber(overview.ai_usage.all_time.requests)} запросов</small></article>
      </div>

      <div className="usage-layout">
        <div className="panel usage-chart-panel">
          <div className="section-heading"><div><p className="eyebrow">ДИНАМИКА</p><h3>Токены по дням</h3></div><span className="usage-breakdown">Входящие {formatNumber(overview.ai_usage.period.prompt_tokens)} · Исходящие {formatNumber(overview.ai_usage.period.completion_tokens)} · Кэш {formatNumber(overview.ai_usage.period.cached_tokens)}</span></div>
          {overview.ai_usage.period.requests === 0 ? <p className="empty">AI-запросов за этот период пока нет</p> : <div className="usage-chart" aria-label="Использование токенов по дням">
            {overview.ai_usage.daily.map((day) => {
              const max = Math.max(...overview.ai_usage.daily.map((item) => item.total_tokens), 1);
              const height = day.total_tokens ? Math.max(5, day.total_tokens / max * 100) : 1;
              return <span key={day.date} className="usage-bar-wrap" title={`${day.date}: ${formatNumber(day.total_tokens)} токенов, ${day.requests} запросов`}><i className="usage-bar" style={{ height: `${height}%` }} /></span>;
            })}
          </div>}
        </div>

        <div className="panel operation-list">
          <p className="eyebrow">ФУНКЦИИ</p><h3>Основные потребители</h3>
          {overview.ai_usage.operations.length === 0 ? <p className="empty">Данных пока нет</p> : <div className="compact-list">{overview.ai_usage.operations.slice(0, 6).map((item) => <div key={`${item.call_name}:${item.model}`}><span><b>{OPERATION_NAMES[item.call_name] || item.call_name}</b><small>{item.model} · {formatNumber(item.requests)} запр.</small></span><strong>{formatNumber(item.total_tokens)}</strong></div>)}</div>}
        </div>
      </div>

      <div className="panel user-usage">
        <div className="section-heading"><div><p className="eyebrow">ПОЛЬЗОВАТЕЛИ</p><h3>Расход токенов за всё время</h3></div><span>{overview.ai_usage.users.length}</span></div>
        {overview.ai_usage.users.length === 0 ? <p className="empty">Статистика появится после первого AI-запроса</p> : <div className="table-wrap"><table><thead><tr><th>Пользователь</th><th>Запросы</th><th>Входящие</th><th>Исходящие</th><th>Всего токенов</th><th>Последняя активность</th></tr></thead><tbody>
          {overview.ai_usage.users.map((item) => <tr key={item.username}><td><strong>{item.display_name}</strong>{item.display_name !== item.username && <small>{item.username}</small>}</td><td>{formatNumber(item.requests)}</td><td>{formatNumber(item.prompt_tokens)}</td><td>{formatNumber(item.completion_tokens)}</td><td><strong>{formatNumber(item.total_tokens)}</strong></td><td>{formatDate(item.last_used)}</td></tr>)}
        </tbody></table></div>}
      </div>
    </section>

    <section>
      <div className="section-heading"><div><p className="eyebrow">DATABASE DEBUG</p><h2>Диагностика базы данных</h2></div><span className="read-only-badge">Только чтение</span></div>
      <div className="database-layout">
        <form className="panel database-console" onSubmit={queryDatabase}>
          <p className="muted database-intro">Запрос выполняется в транзакции PostgreSQL READ ONLY, ограничен 200 строками, 1 МБ вывода и тремя секундами.</p>
          <label>Отдельный секрет БД<input type="password" autoComplete="off" value={databaseSecret} onChange={(event) => setDatabaseSecret(event.target.value)} placeholder="ADMIN_DATABASE_SECRET" /></label>
          <label>SQL<textarea className="sql-editor" spellCheck={false} value={databaseSql} onChange={(event) => setDatabaseSql(event.target.value)} /></label>
          <div className="query-presets">
            <button type="button" onClick={() => setDatabaseSql(DEFAULT_DATABASE_QUERY)}>Список таблиц</button>
            <button type="button" onClick={() => setDatabaseSql("SELECT username, call_name, model, total_tokens, to_timestamp(created) AS created_at\nFROM ai_usage\nORDER BY created DESC\nLIMIT 100")}>Последние AI-запросы</button>
            <button type="button" onClick={() => setDatabaseSql("SELECT * FROM admin_query_audit ORDER BY created DESC LIMIT 50")}>Журнал консоли</button>
          </div>
          {databaseError && <p className="notice error" role="alert">{databaseError}</p>}
          <button className="primary" disabled={databaseBusy || !databaseSecret.trim() || !databaseSql.trim()}>{databaseBusy ? "Выполняем…" : "Выполнить запрос"}</button>
          <p className="audit-note">Каждый успешный и отклонённый запрос записывается в журнал.</p>
        </form>

        <div className="panel database-result">
          <div className="section-heading"><div><p className="eyebrow">РЕЗУЛЬТАТ</p><h3>{databaseResult ? `${databaseResult.row_count} строк` : "SQL-вывод"}</h3></div>{databaseResult && <span>{databaseResult.duration_ms} мс{databaseResult.truncated ? " · обрезано" : ""}</span>}</div>
          {!databaseResult ? <p className="empty">Введите отдельный секрет и выполните диагностический запрос.</p> : <div className="table-wrap query-table"><table><thead><tr>{databaseResult.columns.map((column, index) => <th key={`${column}:${index}`}>{column}</th>)}</tr></thead><tbody>
            {databaseResult.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((value, columnIndex) => <td className={value === null ? "null-cell" : ""} key={columnIndex}>{formatCell(value)}</td>)}</tr>)}
          </tbody></table></div>}
        </div>
      </div>
    </section>

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
