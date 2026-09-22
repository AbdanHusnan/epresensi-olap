export type DashboardKey = "overview" | "attendance" | "departments" | "lateness";

export type DashboardDefinition = {
  key: DashboardKey;
  href: string;
  title: string;
  description: string;
  supersetSlug: string;
  departmentFilter: boolean;
  metrics: readonly string[];
};
