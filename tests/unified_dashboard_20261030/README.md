# Unified dashboard and chart presets — 30 October 2026

The dashboard uses one shared container: daily overview, attendance trend,
and a daily attendance table. The numbered daily/period containers are removed.
Daily filters remain independent of the compact trend controls.

Trend shortcuts: **3D, 7D, 1M, 3M, 6M, 1Y, Custom**. Presets apply immediately,
ending on the selected chart end date. Day windows include both endpoints;
month/year windows use calendar months with month-end clamping. The default is
7D. Custom permits explicit start/end dates. No preset reloads daily metrics.
Missing reporting dates remain missing rather than invented zero values.

Top management has only the department summary table across all three test runs.
Its text search matches department names, without narrowing totals to employees
whose names happen to match. Manager dashboards retain their scoped employee
table. Department-name filters and single-date enforcement remain in place.

Validation: `presets.mts` checks date boundaries; `verify.py` checks saved totals,
role-specific tables, name lookup and daily/period date constraints for each
run; `browser.cjs` checks all presets, independent refreshes, the shared surface,
custom dates, table-only search, employee-table removal and mobile layout.
`mobile.cjs` additionally verifies that all six KPI cards fit inside the mobile embed before the trend. Evidence is stored here in JSON and screenshots.

No simulation data changed. The gradual test remains at batch 1, with 30 October
morning check-ins and zero checkouts.
