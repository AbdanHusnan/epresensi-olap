'use client';
import { useEffect, useState, type FormEvent } from 'react';
import { DashboardSection } from './dashboard-section';
import { DepartmentPicker } from './department-picker';
import { MetabaseFrame } from './metabase-frame';
import { OperationalDashboard } from './operational-dashboard';
import { periodPresets, periodStartFor, type PeriodPreset } from '../lib/period-presets';
import type { TestRun } from '../lib/test-runs';
import type { Role } from '../lib/auth';

type Filters = { run: string; date: string; department: string; departmentName: string; preset: PeriodPreset | 'custom'; start: string; end: string; search: string };
function defaults(run: TestRun): Filters {
  return { run: run.key, date: run.startDate, department: '', departmentName: '', preset: 'custom', start: run.startDate, end: run.endDate, search: '' };
}
function validDate(value: string | null): value is string {
  return !!value && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
}
function readFilters(runs: TestRun[]): Filters {
  const params = new URLSearchParams(window.location.search);
  const defaultRun = runs.find(item => item.key === 'november-2026') || runs[runs.length - 1];
  const run = runs.find(item => item.key === params.get('run')) || defaultRun;
  const value = defaults(run);
  const date = params.get('date'), start = params.get('start'), end = params.get('end');
  if (validDate(date)) value.date = date;
  const department = params.get('department') || '';
  if (/^\d+$/.test(department) && Number.isSafeInteger(Number(department)) && Number(department)>0) {
    value.department = department; value.departmentName = (params.get('departmentName') || `Department ${department}`).slice(0,100);
  }
  const preset = params.get('preset');
  if (preset === 'custom' || periodPresets.includes(preset as PeriodPreset)) value.preset = preset as Filters['preset'];
  if (validDate(end)) value.end = end;
  value.start = value.preset === 'custom' ? (validDate(start) && start <= value.end ? start : run.startDate) : periodStartFor(value.preset, value.end);
  value.search = (params.get('search') || '').slice(0,100);
  return value;
}
function writeFilters(value: Filters) {
  const url = new URL(window.location.href);
  const params = { run:value.run, date:value.date, department:value.department, departmentName:value.departmentName, preset:value.preset, start:value.start, end:value.end, search:value.search };
  for (const [key,item] of Object.entries(params)) { if (item) url.searchParams.set(key,item); else url.searchParams.delete(key); }
  window.history.pushState(null,'',url);
}
const presetLabels: Record<PeriodPreset | 'custom', string> = {
  '3D': '3 Hari',
  '7D': '7 Hari',
  '1M': '1 Bulan',
  '3M': '3 Bulan',
  '6M': '6 Bulan',
  '1Y': '1 Tahun',
  'custom': 'Kustom',
};

export function MetabaseEmbed(props: { role: Role; runs: TestRun[]; publicUrl: string; departmentId?: number }) {
  return props.role === 'director' ? <AnalyticalDashboard runs={props.runs} publicUrl={props.publicUrl}/> : <OperationalDashboard {...props}/>;
}
function AnalyticalDashboard({ runs, publicUrl }: { runs: TestRun[]; publicUrl: string }) {
  const defaultRun = runs.find(item => item.key === 'november-2026') || runs[runs.length - 1];
  const [applied,setApplied] = useState<Filters>(()=>defaults(defaultRun));
  const [draft,setDraft] = useState<Filters>(()=>defaults(defaultRun));
  const [ready,setReady] = useState(false);
  const [filtersExpanded,setFiltersExpanded] = useState(false);
  const [pickerVersion,setPickerVersion] = useState(0);
  const [requestedAt,setRequestedAt] = useState('');
  useEffect(()=>{
    function restore() { const value=readFilters(runs);setApplied(value);setDraft(value);setPickerVersion(v=>v+1);setReady(true); }
    restore(); window.addEventListener('popstate',restore);
    return ()=>window.removeEventListener('popstate',restore);
  },[runs]);
  const run = runs.find(item=>item.key===applied.run) || defaultRun;
  function commit(value: Filters) { setApplied(value);setDraft(value);writeFilters(value);setRequestedAt(new Date().toLocaleTimeString('en-GB',{ timeZone:'Asia/Jakarta', hour:'2-digit', minute:'2-digit' })); }
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = {...draft, start:draft.preset==='custom'?draft.start:periodStartFor(draft.preset,draft.end)};
    if (value.start<=value.end) { commit(value);setFiltersExpanded(false); }
  }
  function reset() { commit(defaults(defaultRun));setPickerVersion(v=>v+1); }
  function preset(value: Filters['preset']) {
    if(value==='custom'){setDraft(current=>({...current,preset:value}));return;}
    commit({...applied,preset:value,start:periodStartFor(value,applied.end)});
  }
  const common = { role:'director' as const, publicUrl, run:applied.run, department:applied.department };
  return <div className="analytical-dashboard">
    <div className="page-heading"><div><p className="eyebrow">RINGKASAN ORGANISASI</p><h1>Dashboard Analitikal</h1><p className="page-description">Memahami rekapitulasi kehadiran lintas departemen dengan visibilitas data terpadu.</p></div>
      <div className="heading-actions"><span className="date-badge">Data per <time dateTime={applied.date}>{applied.date}</time></span><button type="button" className="analytics-button secondary" onClick={()=>{commit({...applied,department:'',departmentName:''});setPickerVersion(v=>v+1);}}>Semua departemen</button></div>
    </div>
    <form id="analytics-filters" className={`analytics-filterbar ${filtersExpanded?'filters-expanded':''}`} onSubmit={apply} aria-label="Filter dashboard">
      <button className="mobile-filter-toggle" type="button" aria-expanded={filtersExpanded} aria-controls="analytics-filters" onClick={()=>setFiltersExpanded(value=>!value)}><strong>Filter</strong><span>{applied.date} · {filtersExpanded?'Tutup':'Ubah'}</span></button>
      <label>Tanggal pelaporan<input type="date" required value={draft.date} onChange={event=>{const date=event.target.value;setDraft(current=>({...current,date,end:date}));}}/></label>
      <DepartmentPicker key={`${draft.run}-${pickerVersion}`} run={draft.run} initialName={draft.departmentName} onChange={(department, name)=>setDraft(current=>({...current,department,departmentName:name || ''}))}/>
      {draft.preset==='custom'&&<label>Awal periode<input type="date" required max={draft.end} value={draft.start} onChange={event=>setDraft(current=>({...current,start:event.target.value}))}/></label>}
      <label>Akhir periode<input type="date" required min={draft.preset==='custom'?draft.start:undefined} value={draft.end} onChange={event=>setDraft(current=>({...current,end:event.target.value}))}/></label>
      <div className="filter-actions"><button className="analytics-button" type="submit" disabled={!ready}>Terapkan</button><button className="analytics-button secondary" type="button" onClick={reset}>Reset</button></div>
    </form>
    <p className="section-caption">Data simulasi presensi · 1–30 November 2026</p>
    <div className="analytics-grid">
      <DashboardSection title="Ringkasan kehadiran" description={`Metrik harian dan tren kehadiran · Snapshot harian · ${applied.date}`} className="overview-section">
        {ready?<MetabaseFrame {...common} id={run.director.overview} section="overview" startDate={applied.date} endDate={applied.date}/>:<InitialSkeleton section="overview"/>}
      </DashboardSection>
      <DashboardSection title="Tren kehadiran" description={`${applied.start} — ${applied.end}`} actions={<div className="period-presets" role="group" aria-label="Periode tren">{[...periodPresets,'custom' as const].map(value=><button type="button" key={value} aria-pressed={draft.preset===value} onClick={()=>preset(value)}>{presetLabels[value]}</button>)}</div>}>
        {ready?<MetabaseFrame {...common} id={run.director.period} section="period" startDate={applied.start} endDate={applied.end}/>:<InitialSkeleton section="period"/>}
      </DashboardSection>
      <DashboardSection title="Kehadiran per departemen" description="Ringkasan departemen dan peringkat Top 10 departemen" actions={<form className="analytics-search" onSubmit={event=>{event.preventDefault();commit({...applied,search:draft.search.trim()});}}>
        <label className="sr-only" htmlFor="table-search">Cari departemen pada tabel</label><input id="table-search" value={draft.search} maxLength={100} placeholder="Nama departemen" onChange={event=>setDraft(current=>({...current,search:event.target.value}))}/><button className="analytics-button secondary" type="submit">Cari tabel</button>{applied.search&&<button className="analytics-button secondary" type="button" onClick={()=>commit({...applied,search:''})}>Hapus</button>}
      </form>}>
        <p className="section-caption">{applied.search&&<>Menampilkan data yang cocok dengan <strong>“{applied.search}”</strong>. </>}Pencarian hanya berlaku untuk tabel harian ini.</p>
        {ready?<MetabaseFrame {...common} id={run.director.tables} section="tables" startDate={applied.date} endDate={applied.date} search={applied.search}/>:<InitialSkeleton section="tables"/>}
      </DashboardSection>
    </div>
    <footer className="analytics-footer"><span>e-Presensi · Wawasan Kehadiran · Zona waktu pelaporan: Asia/Jakarta</span><span>{requestedAt?`Pembaruan terakhir: ${requestedAt} WIB`:'Sumber data: Mart Kehadiran'}</span></footer>
  </div>;
}

function InitialSkeleton({ section }: { section: string }) {
  // Number of shimmer strips to render per section — they fill the CSS grid template.
  // overview: 12 strips → fills 2 rows × 6 columns at wide viewport
  // period:   3 strips  → fills 3-row template (label / chart area / x-axis)
  // tables:   7 strips  → fills 7-row template (table header + 6 body rows)
  const count = section === 'overview' ? 12 : section === 'period' ? 3 : 7;
  return (
    <div className={`metabase-frame frame-${section}`} aria-busy="true">
      <div className="embed-skeleton" role="status">
        <span className="sr-only">Loading {section}</span>
        {Array.from({ length: count }, (_, i) => <div key={i} />)}
      </div>
    </div>
  );
}
