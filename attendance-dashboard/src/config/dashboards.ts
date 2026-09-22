import type { DashboardDefinition } from "@/types/dashboard";

export const dashboards = {
  overview: {
    key: "overview", href: "/", title: "Overview",
    description: "Ringkasan kehadiran dan kedisiplinan pegawai.",
    supersetSlug: "executive-overview", departmentFilter: true,
    metrics: ["Attendance Rate", "On-Time Rate", "Absence Rate", "Average Lateness"],
  },
  attendance: {
    key: "attendance", href: "/attendance", title: "Attendance",
    description: "Pantau tren kehadiran, ketepatan waktu, serta pola WFO dan WFH.",
    supersetSlug: "attendance-analysis", departmentFilter: true,
    metrics: ["Attendance Rate", "On-Time Rate"],
  },
  departments: {
    key: "departments", href: "/departments", title: "Department Performance",
    description: "Bandingkan kehadiran dan kedisiplinan antar departemen.",
    supersetSlug: "department-performance", departmentFilter: false,
    metrics: ["Attendance Rate", "On-Time Rate", "Absence Rate", "Average Lateness"],
  },
  lateness: {
    key: "lateness", href: "/lateness-absence", title: "Lateness & Absence",
    description: "Tinjau tren keterlambatan dan ketidakhadiran pegawai.",
    supersetSlug: "lateness-absence", departmentFilter: true,
    metrics: ["Average Lateness", "Absence Rate"],
  },
} as const satisfies Record<string, DashboardDefinition>;
