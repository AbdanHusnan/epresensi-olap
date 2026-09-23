"use client";

import { useEffect, useRef, useState } from "react";
import { embedDashboard } from "@superset-ui/embedded-sdk";
import type { DashboardKey } from "@/types/dashboard";

export function SupersetDashboard({ dashboardKey, title }: { dashboardKey: DashboardKey; title: string }) {
  const mount = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let disposed = false;
    let embedded: Awaited<ReturnType<typeof embedDashboard>> | undefined;
    const controller = new AbortController();
    const fetchToken = async () => {
      const response = await fetch(`/api/dashboards/${dashboardKey}/guest-token`, {
        method: "POST", credentials: "same-origin", cache: "no-store", signal: controller.signal,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Dashboard gagal dimuat.");
      return data as { token: string; dashboardId: string; supersetUrl: string };
    };
    const start = async () => {
      const initial = await fetchToken();
      if (disposed || !mount.current) return;
      let firstToken: string | undefined = initial.token;
      embedded = await embedDashboard({
        id: initial.dashboardId, supersetDomain: initial.supersetUrl, mountPoint: mount.current,
        referrerPolicy: "strict-origin-when-cross-origin",
        fetchGuestToken: async () => {
          if (firstToken) { const token = firstToken; firstToken = undefined; return token; }
          try { return (await fetchToken()).token; }
          catch (cause) {
            if (!disposed) { setError(cause instanceof Error ? cause.message : "Session berakhir."); embedded?.unmount(); }
            throw cause;
          }
        },
        dashboardUiConfig: { hideTitle: true, hideChartControls: true, filters: { visible: true, expanded: true } },
      });
      if (disposed) { embedded.unmount(); return; }
      const iframe = mount.current.querySelector("iframe");
      if (iframe) iframe.title = title;
      setLoading(false);
    };
    void start().catch(cause => { if (!disposed) { setError(cause instanceof Error ? cause.message : "Dashboard gagal dimuat."); setLoading(false); } });
    return () => { disposed = true; controller.abort(); embedded?.unmount(); };
  }, [dashboardKey, title, attempt]);

  return <section className="analytics-panel" aria-label={`Analitik ${title}`}>
    {loading && !error && <p role="status">Memuat dashboard…</p>}
    {error && <div className="empty-panel" role="alert"><h2>Dashboard belum dapat ditampilkan</h2><p>{error}</p><button type="button" onClick={() => { setError(null); setLoading(true); setAttempt(value => value + 1); }}>Coba lagi</button></div>}
    <div ref={mount} className="superset-mount" hidden={!!error} />
  </section>;
}
