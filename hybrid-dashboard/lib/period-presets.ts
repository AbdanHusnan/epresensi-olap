export const periodPresets = ['3D', '7D', '1M', '3M', '6M', '1Y'] as const;
export type PeriodPreset = typeof periodPresets[number];

// Inclusive trailing windows, anchored to the chart's selected end date.
export function periodStartFor(preset: PeriodPreset, endDate: string): string {
  const end = new Date(`${endDate}T00:00:00Z`);
  if (!Number.isFinite(end.getTime()) || end.toISOString().slice(0,10) !== endDate) throw new Error('Invalid period end date');
  if (preset === '3D' || preset === '7D') {
    end.setUTCDate(end.getUTCDate() - (preset === '3D' ? 2 : 6));
    return end.toISOString().slice(0,10);
  }
  const months = { '1M': 1, '3M': 3, '6M': 6, '1Y': 12 }[preset];
  const start = new Date(end);start.setUTCDate(1);start.setUTCMonth(start.getUTCMonth()-months);
  const last = new Date(start);last.setUTCMonth(last.getUTCMonth()+1,0);
  const lastDay = last.getUTCDate();
  start.setUTCDate(Math.min(end.getUTCDate(),lastDay)+1);
  return start.toISOString().slice(0,10);
}
