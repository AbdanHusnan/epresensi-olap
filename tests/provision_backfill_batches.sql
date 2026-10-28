CREATE SCHEMA IF NOT EXISTS etl_control;

CREATE TABLE IF NOT EXISTS etl_control.backfill_batch (
  batch_id text PRIMARY KEY,
  logical_batch_id text NOT NULL,
  tanggal_mulai date NOT NULL,
  tanggal_selesai date NOT NULL,
  status text NOT NULL CHECK (status IN ('PLANNED', 'RUNNING', 'VALIDATED', 'FAILED')),
  started_at timestamptz,
  completed_at timestamptz,
  catatan text,
  CHECK (tanggal_selesai > tanggal_mulai)
);

-- Tiga sub-batch fisik membentuk satu batch logis tiga bulanan.
INSERT INTO etl_control.backfill_batch
  (batch_id, logical_batch_id, tanggal_mulai, tanggal_selesai, status, catatan)
VALUES
  ('BF_2024_Q1_M01', 'BF_2024_Q1', date '2024-01-01', date '2024-02-01', 'VALIDATED', 'Pilot Januari 2024 sudah direkonsiliasi Raw–Curated.'),
  ('BF_2024_Q1_M02', 'BF_2024_Q1', date '2024-02-01', date '2024-03-01', 'PLANNED', 'Menunggu eksekusi backfill.'),
  ('BF_2024_Q1_M03', 'BF_2024_Q1', date '2024-03-01', date '2024-04-01', 'PLANNED', 'Menunggu eksekusi backfill.')
ON CONFLICT (batch_id) DO NOTHING;
