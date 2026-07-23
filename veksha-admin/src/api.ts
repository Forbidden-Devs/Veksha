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
  features: string[];
  created: number;
  note: string;
};

export type AdminOverview = {
  features: BillingFeature[];
  promos: PromoCode[];
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
};
