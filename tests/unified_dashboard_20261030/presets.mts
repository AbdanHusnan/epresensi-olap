import assert from 'node:assert/strict';
import { periodStartFor } from '../../hybrid-dashboard/lib/period-presets.ts';
for (const [preset,end,start] of [
 ['3D','2026-10-31','2026-10-29'],['7D','2026-10-31','2026-10-25'],
 ['1M','2026-10-31','2026-10-01'],['3M','2026-10-31','2026-08-01'],
 ['6M','2026-10-31','2026-05-01'],['1Y','2026-10-31','2025-11-01'],
 ['3D','2026-01-01','2025-12-30'],['1M','2024-03-31','2024-03-01'],
 ['1M','2024-02-29','2024-01-30'],['1M','2026-03-31','2026-03-01'],
] as const) assert.equal(periodStartFor(preset,end),start);
assert.throws(()=>periodStartFor('3D','2026-02-30'));
assert.throws(()=>periodStartFor('7D',''));
console.log('PASS: inclusive day windows, calendar months, year rollover and leap-day boundaries.');
