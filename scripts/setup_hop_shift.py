"""Add combined shift dimension to the existing Hop dev setup; no credential changes."""
from pathlib import Path
import psycopg
from dotenv import dotenv_values
ROOT = Path(__file__).resolve().parents[1]

def main():
    cfg = dotenv_values(ROOT / '.env')
    def connect(db):
        return psycopg.connect(host=cfg['OLAP_HOST'], port=cfg['OLAP_PORT'],
            user=cfg['OLAP_USER'], password=cfg['OLAP_PASSWORD'], dbname=db)
    with connect('epresensi_analytics_hop_dev') as c:
        c.execute((ROOT / 'sql/hop/dim_shift.sql').read_text())
        c.execute('GRANT SELECT, INSERT, UPDATE ON public.dim_shift TO hop_presensi_writer')
        c.execute('GRANT USAGE, SELECT ON SEQUENCE public.dim_shift_shift_key_seq TO hop_presensi_writer')
    with connect('dbabsen_restore') as c:
        c.execute('GRANT SELECT ON public.m_shift, public.m_jadwal TO hop_presensi_reader')
    print('Ready: epresensi_analytics_hop_dev.public.dim_shift')

if __name__ == '__main__':
    main()
