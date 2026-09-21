# Twice-daily OLAP incremental scheduler

`olap-incremental.timer` runs the chunked incremental pipeline twice per day in
`Asia/Jakarta` (WIB): **10:30** for the morning check-in cutoff and **01:00**
for the evening/final cutoff. The two defaults are intentionally conservative;
change them to match the organisation's actual check-in and last check-out time.

Each run invokes the source read-only incremental pipeline with `--apply`. A
source snapshot and a fixed high watermark are captured once, then source delta
rows are extracted and processed in chunks. A new run is not started while the
service is still active. `Persistent=true` catches one missed timer activation
when the user manager is unavailable; it does not queue overlapping runs.

## Install

Install and activate as the project owner:

```bash
systemctl --user link /home/piramida/OLAP/deploy/systemd/olap-incremental.service /home/piramida/OLAP/deploy/systemd/olap-incremental.timer
systemctl --user daemon-reload
systemctl --user enable --now olap-incremental.timer
systemctl --user list-timers olap-incremental.timer
```

Inspect execution and disable the schedule:

```bash
journalctl --user -u olap-incremental.service -n 100 --no-pager
systemctl --user disable --now olap-incremental.timer
```

## Change the WIB schedule

Use a user drop-in instead of editing the tracked timer file. The empty
`OnCalendar=` resets both defaults, then the following lines install the desired
cutoffs. For example, 11:00 and 01:30 WIB:

```bash
systemctl --user edit olap-incremental.timer
```

```ini
[Timer]
OnCalendar=
OnCalendar=*-*-* 11:00:00 Asia/Jakarta
OnCalendar=*-*-* 01:30:00 Asia/Jakarta
```

Then apply and verify it:

```bash
systemctl --user daemon-reload
systemctl --user restart olap-incremental.timer
systemctl --user list-timers olap-incremental.timer
```

## Change chunk and recomputation sizes

The optional environment file `/home/piramida/.config/olap/incremental.env` is
read by the service. Create it with owner-only permissions and set command-line
arguments there; it contains no database credentials:

```ini
OLAP_INCREMENTAL_ARGS=--chunk-size 1000 --batch-size 1000 --overlap-minutes 5
```

- `--chunk-size` bounds source delta rows held for one extraction/transform pass.
- `--batch-size` bounds employee-days recomputed at once for a calendar date.
- `--overlap-minutes` remains a timestamp lookback for permission changes.

Start with 1,000 for both sizes, inspect duration/RAM in journald, then adjust
only after observing real runs.

## Coordination and daily facts

Master, incremental, and initial-load use the same advisory lock. Do not enable
the supplied `olap-master.timer` at the same time as this two-cutoff timer unless
you deliberately schedule it outside these windows; a conflicting run fails
fast and is not queued.

Incremental processing responds to changed attendance/permission rows only. It
does not create a `TIDAK_ABSEN` row for a new employee-day with no event or
leave. Keep a separately scheduled daily master/population job if the dashboard
needs those rows, and place it after the final cutoff.

For operation after logout and automatic start on boot, the account needs
systemd lingering enabled by the host administrator. Check with:

```bash
loginctl show-user piramida -p Linger
```
