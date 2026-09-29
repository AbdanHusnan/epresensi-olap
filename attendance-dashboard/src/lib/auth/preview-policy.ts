// Temporary development access while the SSO contract is pending.
export function allowLocalPreview(env: Record<string, string | undefined>, origin: string | null, host: string | null) {
  if (env.NODE_ENV !== "development" || env.DASHBOARD_LOCAL_PREVIEW !== "true" || !origin) return false;
  const allowedOrigins = [env.APP_ORIGIN, env.APP_LOCALHOST_ORIGIN].filter((value): value is string => Boolean(value));
  if (!allowedOrigins.includes(origin)) return false;
  try {
    const url = new URL(origin);
    return url.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)
      && url.origin === origin && host === url.host;
  } catch { return false; }
}
