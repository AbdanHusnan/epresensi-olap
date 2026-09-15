"""Read-only schema and source readiness checks for initial load."""
from psycopg import sql

SOURCE_COLUMNS = {
    'm_departemen': 'id kode nama_departemen',
    'm_pegawai': 'id departemen nip nama created_at updated_at',
    'm_shift': 'id departemen_id nama is_flexible created_at',
    'm_jadwal': 'id jenis hari jam_masuk jam_keluar jam_masuk_awal jam_keluar_akhir created_at',
    'm_tipe_ijin': 'id nama',
    'm_jenis_ijin': 'id tipe_id kode nama created_at',
    'm_hari_libur': 'tanggal keterangan',
    't_checkinout': 'id pegawai_id departemen work_code is_wfh created_at updated_at',
    't_libur_shift': 'id departemen_id pegawai_id tanggal keterangan created_at updated_at',
    't_perizinan': 'id pegawai_id tipe_ijin jenis_ijin alasan approval approval_at tgl_ijin tgl_ijin_sampai created_at updated_at',
    'm_user': 'id pegawai_id is_active last_login updated_at created_at',
}
TARGET_COLUMNS = {
    'dim_departemen': 'departemen_id kode_departemen nama_departemen source_hash',
    'dim_pegawai': 'pegawai_id departemen_id nip nama_pegawai status_aktif source_updated_at',
    'dim_jadwal_kerja': 'jadwal_id shift_id departemen_id nama_shift hari jam_masuk jam_keluar jam_masuk_awal jam_keluar_akhir is_flexible source_updated_at',
    'dim_jenis_izin': 'jenis_izin_id tipe_izin_id kode_jenis_izin nama_jenis_izin nama_tipe_izin source_updated_at',
    'dim_calendar': 'tanggal tahun bulan nama_bulan hari nama_hari minggu_ke kuartal is_weekend is_hari_libur keterangan_libur',
    'fact_perizinan': 'perizinan_id pegawai_id departemen_id jenis_izin_id tanggal_pengajuan tanggal_mulai tanggal_selesai jumlah_hari status_pengajuan is_approved is_valid_leave alasan source_updated_at',
    'fact_kehadiran': 'pegawai_id tanggal departemen_id jadwal_id is_expected_workday is_libur_shift waktu_masuk waktu_pulang has_masuk has_pulang has_valid_leave perizinan_id status_kehadiran is_wfh is_wfo is_terlambat menit_terlambat is_pulang_awal menit_pulang_awal is_complete_attendance jumlah_event source_updated_at',
    'analytical_user': 'user_id pegawai_id is_active last_login pernah_login source_updated_at',
}
CONTROL_COLUMNS = {
    'pipeline_state': 'pipeline_name',
    'pipeline_runs': 'run_id pipeline_name status finished_at rows_extracted rows_inserted rows_updated',
}


def check_columns(conn, schema, contract, label):
    columns = {}
    for table, column in conn.execute(
        'SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = %s',
        (schema,),
    ):
        columns.setdefault(table, set()).add(column)
    errors = []
    for table, required in contract.items():
        if table not in columns:
            errors.append(f'{label}: tabel {schema}.{table} tidak tersedia/terlihat oleh user koneksi')
        else:
            missing = set(required.split()) - columns[table]
            if missing:
                errors.append(f'{label}: {schema}.{table} kekurangan kolom: {", ".join(sorted(missing))}')
    return errors


def check_requirements(source, target, start_date, end_date):
    if start_date > end_date:
        raise ValueError('start_date must be on or before end_date')
    source_errors = check_columns(source, 'public', SOURCE_COLUMNS, 'OLTP')
    errors = source_errors + check_columns(target, 'public', TARGET_COLUMNS, 'OLAP')
    errors += check_columns(target, 'etl_control', CONTROL_COLUMNS, 'OLAP')
    counts, warnings = {}, []
    if not source_errors:
        for table in SOURCE_COLUMNS:
            if table == 't_checkinout':
                counts[table] = source.execute(
                    'SELECT count(*) FROM public.t_checkinout WHERE work_code = 1 '
                    "AND created_at >= %s::date AND created_at < (%s::date + INTERVAL '1 day')",
                    (start_date, end_date),
                ).fetchone()[0]
            else:
                counts[table] = source.execute(sql.SQL('SELECT count(*) FROM {}').format(
                    sql.Identifier('public', table))).fetchone()[0]
        for table in ('m_departemen', 'm_pegawai', 'm_shift', 'm_jadwal', 'm_tipe_ijin', 'm_jenis_ijin'):
            if not counts[table]:
                errors.append(f'OLTP: {table} kosong; isi master dummy sebelum initial load')
        for table in ('t_checkinout', 't_perizinan', 't_libur_shift', 'm_hari_libur', 'm_user'):
            if not counts[table]:
                warnings.append(f'OLTP: {table} tidak memiliki data untuk cakupan load')
        if not counts['t_checkinout']:
            warnings.append('Tanpa event absensi, fact_kehadiran tetap dibuat per pegawai per hari; '
                            'hari kerja tanpa izin menjadi TIDAK_ABSEN')
    return {
        'ready': not errors, 'errors': errors, 'warnings': warnings,
        'source_counts': counts,
        'expected_employee_days': counts.get('m_pegawai', 0) * ((end_date - start_date).days + 1),
        'scope': list(TARGET_COLUMNS),
    }
