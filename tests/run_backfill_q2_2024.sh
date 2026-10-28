#!/usr/bin/env bash
set -euo pipefail

run_month() {
  local batch_id="$1"
  local start_date="$2"
  local end_date="$3"

  psql -v ON_ERROR_STOP=1 -U admin_staging -d staging_bkd \
    -c "UPDATE etl_control.backfill_batch SET status='RUNNING', started_at=clock_timestamp(), completed_at=NULL WHERE batch_id='${batch_id}';"

  psql -v ON_ERROR_STOP=1 \
    -v batch_id="${batch_id}" \
    -v start_date="${start_date}" \
    -v end_date="${end_date}" \
    -U admin_staging -d staging_bkd \
    -f /tmp/backfill_curated_batch.sql

  psql -v ON_ERROR_STOP=1 -U admin_staging -d staging_bkd \
    -c "UPDATE etl_control.backfill_batch SET status='LOADED', completed_at=clock_timestamp(), catatan='Commit sukses; menunggu rekonsiliasi Raw–Curated.' WHERE batch_id='${batch_id}';"
}

run_month BF_2024_Q2_M04 2024-04-01 2024-05-01
run_month BF_2024_Q2_M05 2024-05-01 2024-06-01
run_month BF_2024_Q2_M06 2024-06-01 2024-07-01
