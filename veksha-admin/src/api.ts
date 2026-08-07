export type BillingFeature = {
  feature: string;
  stars_monthly: number;
  updated: number;
};

export type PromoCode = {
  code: string;
  days: number;
  max_redemptions: number;
  redemptions: number;
  paused: boolean;
  features: string[];
  created: number;
  note: string;
};

export type AdminOverview = {
  features: BillingFeature[];
  promos: PromoCode[];
  ai_usage: AiUsageStats;
};

export type AiUsageSummary = {
  requests: number;
  active_users: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  reasoning_tokens: number;
};

export type AiUsageUser = Omit<AiUsageSummary, "active_users"> & {
  username: string;
  display_name: string;
  last_used: number;
};

export type AiUsageStats = {
  period_days: number;
  all_time: AiUsageSummary;
  period: AiUsageSummary;
  daily: Array<{ date: string; requests: number; active_users: number; total_tokens: number }>;
  users: AiUsageUser[];
  operations: Array<{ call_name: string; model: string; requests: number; total_tokens: number }>;
};

export type DatabaseQueryResult = {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
};

export type PromoDraft = {
  code: string;
  days: number;
  max_redemptions: number;
  note: string;
  features: string[];
};

export class AdminApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

const baseUrl = (import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export function normalizedCode(value: string): string {
  return value.trim().toUpperCase();
}

async function request<T>(path: string, secret: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Veksha-Admin-Secret": secret,
      ...init?.headers,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new AdminApiError(response.status, body.detail || `Ошибка сервера (${response.status})`);
  }
  return body as T;
}

export const adminApi = {
  overview: (secret: string) =>
    request<AdminOverview>("/api/billing/admin/overview", secret),
  setPrice: (secret: string, feature: string, starsMonthly: number) =>
    request<BillingFeature>(`/api/billing/features/${encodeURIComponent(feature)}/price`, secret, {
      method: "PUT",
      body: JSON.stringify({ stars_monthly: starsMonthly }),
    }),
  createPromo: (secret: string, draft: PromoDraft) =>
    request<{ ok: boolean }>("/api/billing/promo/create", secret, {
      method: "POST",
      body: JSON.stringify({ ...draft, code: normalizedCode(draft.code) }),
    }),
  setPromoPaused: (secret: string, code: string, paused: boolean) =>
    request<{ ok: boolean; code: string; paused: boolean }>(
      `/api/billing/promo/${encodeURIComponent(normalizedCode(code))}/pause`,
      secret,
      { method: "PUT", body: JSON.stringify({ paused }) },
    ),
  databaseQuery: (secret: string, databaseSecret: string, sql: string) =>
    request<DatabaseQueryResult>("/api/admin/database/query", secret, {
      method: "POST",
      headers: { "X-Veksha-Database-Secret": databaseSecret },
      body: JSON.stringify({ sql }),
    }),
};
