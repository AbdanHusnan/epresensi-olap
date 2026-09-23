import "server-only";
import { getSupersetConfig } from "./config";
import type { DashboardKey } from "@/types/dashboard";

export async function createPreviewGuestToken(key: DashboardKey) {
  const config = getSupersetConfig();
  const id = config.dashboardIds[key];
  if (!id || !config.url || !config.internalUrl || !config.username || !config.password) throw new Error("SUPERSET_NOT_CONFIGURED");
  const cookies = new Map<string, string>();
  let csrf = "";
  const post = async (path: string, body: unknown, token?: string) => {
    const response = await fetch(`${config.internalUrl!.replace(/\/$/, "")}${path}`, {
      method: body === undefined ? "GET" : "POST", cache: "no-store", redirect: "error", signal: AbortSignal.timeout(15_000),
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(csrf ? { "X-CSRFToken": csrf } : {}), ...(cookies.size ? { Cookie: [...cookies].map(([name, value]) => `${name}=${value}`).join("; ") } : {}) },
      body: JSON.stringify(body),
    });
    for (const cookie of response.headers.getSetCookie()) {
      const pair = cookie.split(";", 1)[0];
      const separator = pair.indexOf("=");
      if (separator > 0) cookies.set(pair.slice(0, separator), pair.slice(separator + 1));
    }
    if (!response.ok) throw new Error("SUPERSET_UNAVAILABLE");
    return response.json();
  };
  const login = await post("/api/v1/security/login", { username: config.username, password: config.password, provider: "db", refresh: false });
  if (typeof login.access_token !== "string" || !login.access_token) throw new Error("SUPERSET_LOGIN_FAILED");
  const csrfResponse = await post("/api/v1/security/csrf_token/", undefined, login.access_token);
  if (typeof csrfResponse.result !== "string" || !csrfResponse.result) throw new Error("SUPERSET_CSRF_FAILED");
  csrf = csrfResponse.result;
  const guest = await post("/api/v1/security/guest_token/", {
    user: { username: "local-dashboard-preview" }, resources: [{ type: "dashboard", id }], rls: [],
  }, login.access_token);
  if (typeof guest.token !== "string" || !guest.token) throw new Error("SUPERSET_TOKEN_FAILED");
  return { token: guest.token, dashboardId: id, supersetUrl: config.url };
}
