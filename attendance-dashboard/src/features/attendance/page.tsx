import { DashboardPage } from "@/components/dashboard/dashboard-page";
import { dashboards } from "@/config/dashboards";

export default function Page() {
  return <DashboardPage dashboard={dashboards.attendance} />;
}
