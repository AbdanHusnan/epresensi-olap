// Temporary development access while the SSO contract is pending.
export function allowLocalPreview(env: Record<string, string | undefined>, origin: string | null, host: string | null) {
  if (env.NODE_ENV !== "development" || env.DASHBOARD_LOCAL_PREVIEW !== "true") return false;
  if (!env.APP_ORIGIN || origin !== env.APP_ORIGIN) return false;
  try {
    const url = new URL(env.APP_ORIGIN);
    return url.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)
      && url.origin === env.APP_ORIGIN && host === url.host;
  } catch { return false; }
}
