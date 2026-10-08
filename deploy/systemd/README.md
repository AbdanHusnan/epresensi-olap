# Layanan dashboard

Folder ini hanya menyimpan `olap-dashboard.service` untuk dashboard Next.js lokal.
Unit master/incremental ETL Python telah dihapus dan scheduler lama dinonaktifkan.

Panduan pipeline dan runner Apache Hop ada di [hop/README.md](../../hop/README.md).
Backfill Hop berjalan melalui runner, belum dipasang sebagai timer systemd.

Periksa dashboard yang sudah terpasang dengan:

```bash
systemctl --user status olap-dashboard.service
journalctl --user -u olap-dashboard.service -n 100 --no-pager
```
