"""Read-only hierarchy audit. Run: .venv/bin/python scripts/audit_departemen_mapping.py."""
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from report_paths import report_path
from zoneinfo import ZoneInfo

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / '.env')
    with psycopg.connect(
        host=os.environ['OLAP_HOST'], port=os.environ['OLAP_PORT'],
        user=os.environ['OLAP_USER'], password=os.environ['OLAP_PASSWORD'],
        dbname='dbabsen_restore', row_factory=dict_row,
        options='-c default_transaction_read_only=on -c statement_timeout=60000',
    ) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        rows = conn.execute('SELECT id, kode, nama_departemen, kode_lengkap, parent, '
                            'opd_parent, unit_kerja_induk FROM public.m_departemen ORDER BY id').fetchall()
        views = conn.execute("SELECT viewname, definition FROM pg_views WHERE schemaname='public' "
                             "AND (definition ILIKE '%opd_parent%' OR definition ILIKE '%unit_kerja_induk%')").fetchall()
    by_id = {r['id']: r for r in rows}
    result = {'database': 'dbabsen_restore', 'read_only': True,
              'checked_at': datetime.now(ZoneInfo('Asia/Jakarta')).isoformat(),
              'rows': len(rows), 'fields': {}, 'view_evidence': views}
    for field in ('parent', 'opd_parent', 'unit_kerja_induk'):
        counts = Counter()
        missing = []
        cycles = set()
        for r in rows:
            v = r[field]
            kind = ('null' if v is None else 'zero' if v == 0 else
                    'self' if v == r['id'] else 'matched_other' if v in by_id else 'missing')
            counts[kind] += 1
            if kind == 'missing':
                missing.append({'id': r['id'], 'reference': v})
            path, seen = [], {}
            node = r['id']
            while node in by_id and node not in seen:
                seen[node] = len(path)
                path.append(node)
                node = by_id[node][field]
            if node in seen:
                cycles.add(tuple(sorted(path[seen[node]:])))
        result['fields'][field] = {'counts': dict(counts), 'missing_references': missing,
                                   'cycles': sorted(cycles)}
    roots = Counter()
    agreement = Counter()
    for r in rows:
        node, seen, ancestors = r['id'], set(), []
        while node in by_id and node not in seen:
            seen.add(node)
            ancestors.append(node)
            node = by_id[node]['parent']
        root = ancestors[-1] if node in (None, 0) else None
        roots[root] += 1
        v = r['opd_parent']
        if v not in (None, 0):
            agreement['nonzero_opd'] += 1
            agreement['equals_parent_root'] += v == root
            agreement['in_parent_chain_including_self'] += v in ancestors
    result['opd_vs_parent'] = dict(agreement)
    result['parent_roots'] = [{'id': k, 'rows': v} for k, v in roots.items()]
    for field in ('kode', 'nama_departemen', 'kode_lengkap'):
        values = Counter(r[field] for r in rows if r[field] is not None)
        result[field] = {'null': sum(r[field] is None for r in rows),
                         'blank': sum(isinstance(r[field], str) and not r[field].strip() for r in rows),
                         'duplicate_groups': sum(n > 1 for n in values.values())}
    result['kode_contains_hapus'] = sum('HAPUS' in (r['kode'] or '').upper() for r in rows)
    result['samples'] = rows[:10]
    result['unit_kerja_induk_populated'] = [
        {'source': r, 'referenced': by_id.get(r['unit_kerja_induk'])}
        for r in rows if r['unit_kerja_induk'] not in (None, 0)
    ]
    result['opd_outside_parent_chain_samples'] = []
    for r in rows:
        node, ancestors = r['id'], set()
        while node in by_id and node not in ancestors:
            ancestors.add(node)
            node = by_id[node]['parent']
        if r['opd_parent'] not in (None, 0) and r['opd_parent'] not in ancestors:
            result['opd_outside_parent_chain_samples'].append(r)
            if len(result['opd_outside_parent_chain_samples']) == 5:
                break
    out = report_path('audit-mapping-departemen.json')
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('view_evidence', 'samples', 'parent_roots', 'fields', 'opd_outside_parent_chain_samples')}, ensure_ascii=False))
    print(json.dumps({k: {'counts': v['counts'], 'cycles': v['cycles'], 'missing_sample': v['missing_references'][:5]} for k, v in result['fields'].items()}))
    print('Views:', [v['viewname'] for v in views])
    print('Evidence:', out)


if __name__ == '__main__':
    main()
