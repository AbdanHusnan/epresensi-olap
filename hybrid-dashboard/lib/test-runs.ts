import registry from './test-runs.json';
import type { Role } from './auth';
export type TestRun = { key: string; label: string; startDate: string; endDate: string; note: string; director: { overview: number; tables: number; period: number }; manager: { overview: number; tables: number; period: number } };
export const testRuns: TestRun[] = registry;
export function testRun(key: unknown): TestRun | undefined { return testRuns.find(run => run.key === key); }
export function runDashboardId(run: TestRun, role: Role, section: 'overview' | 'tables' | 'period'): number { return run[role][section]; }
