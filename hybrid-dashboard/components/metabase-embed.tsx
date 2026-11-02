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
  return { run: run.key, date: run.startDate, department: '', departmentName: '', preset: '7D', start: periodStartFor('7D', run.endDate), end: run.endDate, search: '' };
}
function validDate(value: string | null): value is string {
  return !!value && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
}
function readFilters(runs: TestRun[]): Filters {
  const params = new URLSearchParams(window.location.search);
  const run = runs.find(item => item.key === params.get('run')) || runs[0];
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
  value.start = value.preset === 'custom' && validDate(start) && start <= value.end ? start : periodStartFor(value.preset === 'custom' ? '7D' : value.preset, value.end);
  value.search = (params.get('search') || '').slice(0,100);
  return value;
}
function writeFilters(value: Filters) {
  const url = new URL(window.location.href);
  const params = { run:value.run, date:value.date, department:value.department, departmentName:value.departmentName, preset:value.preset, start:value.start, end:value.end, search:value.search };
  for (const [key,item] of Object.entries(params)) { if (item) url.searchParams.set(key,item); else url.searchParams.delete(key); }
  window.history.pushState(null,'',url);
}
export function MetabaseEmbed(props: { role: Role; runs: TestRun[]; publicUrl: string }) {
  return props.role === 'director' ? <AnalyticalDashboard runs={props.runs} publicUrl={props.publicUrl}/> : <OperationalDashboard {...props}/>;
}
function AnalyticalDashboard({ runs, publicUrl }: { runs: TestRun[]; publicUrl: string }) {
  const [applied,setApplied] = useState<Filters>(()=>defaults(runs[0]));
  const [draft,setDraft] = useState<Filters>(()=>defaults(runs[0]));
  const [ready,setReady] = useState(false);
  const [dismissed,setDismissed] = useState(false);
  const [filtersExpanded,setFiltersExpanded] = useState(false);
  const [pickerVersion,setPickerVersion] = useState(0);
  const [requestedAt,setRequestedAt] = useState('');
  useEffect(()=>{
    function restore() { const value=readFilters(runs);setApplied(value);setDraft(value);setPickerVersion(v=>v+1);setReady(true); }
    restore(); window.addEventListener('popstate',restore);
    return ()=>window.removeEventListener('popstate',restore);
  },[runs]);
  const run = runs.find(item=>item.key===applied.run)!;
  const previewRun = runs.find(item=>item.key===draft.run)!;
  function commit(value: Filters) { setApplied(value);setDraft(value);writeFilters(value);setRequestedAt(new Date().toLocaleTimeString('en-GB',{ timeZone:'Asia/Jakarta', hour:'2-digit', minute:'2-digit' })); }
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = {...draft, start:draft.preset==='custom'?draft.start:periodStartFor(draft.preset,draft.end)};
    if (value.start<=value.end) { commit(value);setFiltersExpanded(false); }
  }
  function reset() { commit(defaults(runs[0]));setPickerVersion(v=>v+1);setDismissed(false); }
  function preset(value: Filters['preset']) {
    if(value==='custom'){setDraft(current=>({...current,preset:value}));return;}
    commit({...applied,preset:value,start:periodStartFor(value,applied.end)});
  }
  const common = { role:'director' as const, publicUrl, run:applied.run, department:applied.department };
  return <div className="analytical-dashboard">
    <div className="page-heading"><div><p className="eyebrow">THE ORGANIZATION AT A GLANCE</p><h1>Analytical Dashboard</h1><p className="page-description">Understand attendance across departments, with a shared view of the numbers.</p></div>
      <div className="heading-actions"><span className="date-badge">Data per <time dateTime={applied.date}>{applied.date}</time></span><button type="button" className="analytics-button secondary" onClick={()=>{commit({...applied,department:'',departmentName:''});setPickerVersion(v=>v+1);}}>All departments</button></div>
    </div>
    {!dismissed&&<aside className="test-run-banner" aria-label="Test run notice"><span className="banner-dot"/><div><strong>Test data · {run.label}</strong><span title={run.note}>{run.note}</span></div><span className="banner-tag">PREVIEW</span><button type="button" aria-label="Dismiss test run banner" onClick={()=>setDismissed(true)}>×</button></aside>}
    <form id="analytics-filters" className={`analytics-filterbar ${filtersExpanded?'filters-expanded':''}`} onSubmit={apply} aria-label="Dashboard filters">
      <button className="mobile-filter-toggle" type="button" aria-expanded={filtersExpanded} aria-controls="analytics-filters" onClick={()=>setFiltersExpanded(value=>!value)}><strong>Filters</strong><span>{applied.date} · {filtersExpanded?'Close':'Edit'}</span></button>
      <label>Test run<select value={draft.run} onChange={event=>{const next=runs.find(item=>item.key===event.target.value)!;setDraft(defaults(next));setPickerVersion(v=>v+1);setDismissed(false);}}>{runs.map(item=><option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
      <label>Reporting date<input type="date" required value={draft.date} onChange={event=>{const date=event.target.value;setDraft(current=>({...current,date,end:date}));}}/></label>
      <DepartmentPicker key={`${draft.run}-${pickerVersion}`} run={draft.run} initialName={draft.departmentName} onChange={(department, name)=>setDraft(current=>({...current,department,departmentName:name || ''}))}/>
      {draft.preset==='custom'&&<label>Period start<input type="date" required max={draft.end} value={draft.start} onChange={event=>setDraft(current=>({...current,start:event.target.value}))}/></label>}
      <label>Period end<input type="date" required min={draft.preset==='custom'?draft.start:undefined} value={draft.end} onChange={event=>setDraft(current=>({...current,end:event.target.value}))}/></label>
      <div className="filter-actions"><button className="analytics-button" type="submit" disabled={!ready}>Apply</button><button className="analytics-button secondary" type="button" onClick={reset}>Reset</button></div>
      {draft.run!==applied.run&&<p className="filter-pending" role="status">Apply to view {previewRun.label}.</p>}
    </form>
    <div className="analytics-grid">
      <DashboardSection title="Attendance overview" description={`Daily metrics and attendance trends · Daily snapshot · ${applied.date}`} className="overview-section">
        {ready?<MetabaseFrame {...common} id={run.director.overview} section="overview" startDate={applied.date} endDate={applied.date}/>:<InitialSkeleton section="overview"/>}
      </DashboardSection>
      <DashboardSection title="Attendance trend" description={`${applied.start} — ${applied.end}`} actions={<div className="period-presets" role="group" aria-label="Trend period">{[...periodPresets,'custom' as const].map(value=><button type="button" key={value} aria-pressed={draft.preset===value} onClick={()=>preset(value)}>{value==='custom'?'Custom':value}</button>)}</div>}>
        {ready?<MetabaseFrame {...common} id={run.director.period} section="period" startDate={applied.start} endDate={applied.end}/>:<InitialSkeleton section="period"/>}
      </DashboardSection>
      <DashboardSection title="Department attendance" description="Department summary and Top 10 departments" actions={<form className="analytics-search" onSubmit={event=>{event.preventDefault();commit({...applied,search:draft.search.trim()});}}>
        <label className="sr-only" htmlFor="table-search">Find a department in the table</label><input id="table-search" value={draft.search} maxLength={100} placeholder="Department name" onChange={event=>setDraft(current=>({...current,search:event.target.value}))}/><button className="analytics-button secondary" type="submit">Search table</button>{applied.search&&<button className="analytics-button secondary" type="button" onClick={()=>commit({...applied,search:''})}>Clear</button>}
      </form>}>
        <p className="section-caption">{applied.search&&<>Table matching <strong>“{applied.search}”</strong>. </>}Search applies only to this daily table.</p>
        {ready?<MetabaseFrame {...common} id={run.director.tables} section="tables" startDate={applied.date} endDate={applied.date} search={applied.search}/>:<InitialSkeleton section="tables"/>}
      </DashboardSection>
    </div>
    <footer className="analytics-footer"><span>e-Presensi · Attendance insights · Reporting timezone: Asia/Jakarta</span><span>{requestedAt?`Last refresh requested: ${requestedAt} WIB`:'Source: Metabase · Attendance mart'} · Powered by Metabase</span></footer>
  </div>;
}

function InitialSkeleton({section}:{section:string}) {
  return <div className={`metabase-frame frame-${section}`} aria-busy="true"><div className="embed-skeleton" role="status"><span className="sr-only">Loading {section}</span><div/><div/><div/></div></div>;
}
