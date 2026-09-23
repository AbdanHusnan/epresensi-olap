import "server-only";
import type { DashboardKey } from "@/types/dashboard";

// Only server code may read integration settings. No admin credentials in browser code.
export function getSupersetConfig() {
  const dashboardIds: Record<DashboardKey, string | undefined> = {
    overview: process.env.SUPERSET_OVERVIEW_ID,
    attendance: process.env.SUPERSET_ATTENDANCE_ID,
    departments: process.env.SUPERSET_DEPARTMENTS_ID,
    lateness: process.env.SUPERSET_LATENESS_ID,
  };
  return {
    url: process.env.SUPERSET_URL,
    internalUrl: process.env.SUPERSET_INTERNAL_URL || process.env.SUPERSET_URL,
    username: process.env.SUPERSET_SERVICE_USERNAME,
    password: process.env.SUPERSET_SERVICE_PASSWORD,
    dashboardIds,
  };
}
