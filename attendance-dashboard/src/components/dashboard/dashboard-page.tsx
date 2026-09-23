import type { DashboardDefinition } from "@/types/dashboard";
import { SupersetDashboard } from "./superset-dashboard";

export function DashboardPage({ dashboard }: { dashboard: DashboardDefinition }) {
  return <>
    <header className="page-heading">
      <p className="eyebrow">PRESENSI PEGAWAI</p>
      <h1>{dashboard.title}</h1>
      <p>{dashboard.description}</p>
    </header>
    <SupersetDashboard dashboardKey={dashboard.key} title={dashboard.title} />
  </>;
}
