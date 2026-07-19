export interface AiBlocklist {
  sites: string[];
  pages: string[];
  allowedPages: string[];
}

export const EMPTY_AI_BLOCKLIST: AiBlocklist = { sites: [], pages: [], allowedPages: [] };

export function normalizeAiBlocklist(value: unknown): AiBlocklist {
  const raw = (value && typeof value === "object" ? value : {}) as Partial<AiBlocklist>;
  const strings = (items: unknown) => Array.isArray(items)
    ? [...new Set(items.filter((item): item is string => typeof item === "string" && item.length > 0))]
    : [];
  return { sites: strings(raw.sites), pages: strings(raw.pages), allowedPages: strings(raw.allowedPages) };
}

export function pageKey(rawUrl: string): string | null {
  try {
    const url = new URL(rawUrl);
    if (!/^https?:$/.test(url.protocol)) return null;
    return `${url.origin}${url.pathname}${url.search}`;
  } catch {
    return null;
  }
}

export function siteKey(rawUrl: string): string | null {
  try {
    const withProtocol = /^[a-z][a-z\d+.-]*:/i.test(rawUrl) ? rawUrl : `https://${rawUrl}`;
    const url = new URL(withProtocol);
    if (!url.hostname) return null;
    return url.hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return null;
  }
}

export function isAiBlocked(rawUrl: string, list: AiBlocklist): boolean {
  const page = pageKey(rawUrl);
  const site = siteKey(rawUrl);
  if (!page || !site) return false;
  if (list.allowedPages.includes(page)) return false;
  return list.pages.includes(page) || list.sites.includes(site);
}

export function blockAiOnPage(list: AiBlocklist, rawUrl: string): AiBlocklist {
  const page = pageKey(rawUrl);
  if (!page) return list;
  return {
    ...list,
    pages: [...new Set([...list.pages, page])],
    allowedPages: list.allowedPages.filter((item) => item !== page),
  };
}

export function blockAiOnSite(list: AiBlocklist, rawUrl: string): AiBlocklist {
  const site = siteKey(rawUrl);
  if (!site) return list;
  return { ...list, sites: [...new Set([...list.sites, site])] };
}

export function enableAiOnPage(list: AiBlocklist, rawUrl: string): AiBlocklist {
  const page = pageKey(rawUrl);
  const site = siteKey(rawUrl);
  if (!page || !site) return list;
  return {
    ...list,
    pages: list.pages.filter((item) => item !== page),
    allowedPages: list.sites.includes(site)
      ? [...new Set([...list.allowedPages, page])]
      : list.allowedPages.filter((item) => item !== page),
  };
}

export function enableAiOnSite(list: AiBlocklist, rawUrl: string): AiBlocklist {
  const site = siteKey(rawUrl);
  if (!site) return list;
  const belongsToSite = (page: string) => siteKey(page) === site;
  return {
    sites: list.sites.filter((item) => item !== site),
    pages: list.pages.filter((item) => !belongsToSite(item)),
    allowedPages: list.allowedPages.filter((item) => !belongsToSite(item)),
  };
}
