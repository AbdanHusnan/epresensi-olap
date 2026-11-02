'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';

let scriptReady: Promise<void> | undefined;
function loadScript(instanceUrl: string): Promise<void> {
  if (scriptReady) return scriptReady;
  window.metabaseConfig = { isGuest: true, instanceUrl, guestEmbedProviderUri: '/api/metabase-token' };
  scriptReady = new Promise((resolve,reject) => {
    const script = document.createElement('script');
    script.src = `${instanceUrl}/app/embed.js`; script.async = true;
    script.onload = () => resolve();
    script.onerror = () => { script.remove(); scriptReady = undefined; reject(new Error('Unable to connect to the dashboard service.')); };
    document.head.appendChild(script);
  });
  return scriptReady;
}
import { periodPresets, periodStartFor, type PeriodPreset } from '../lib/period-presets';
import { DepartmentPicker } from './department-picker';
import type { TestRun } from '../lib/test-runs';
import type { Role } from '../lib/auth';

function DashboardSection({ id, role, publicUrl, run, section, startDate, endDate, department, search = '' }: { id: number; role: Role; publicUrl: string; run: string; section: 'overview' | 'tables' | 'period'; startDate: string; endDate: string; department: string; search?: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState('');
  const [attempt,setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 45000);
    setLoading(true);setError('');
    async function load() {
      try {
        const host = new URL(window.location.origin);host.port='3101';
        const instanceUrl = publicUrl || host.origin;
        const response = await fetch('/api/metabase-token', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({entityType:'dashboard',entityId:id,run,section,startDate,endDate,department,search}), signal:controller.signal });
        if(response.status===401){window.location.assign('/login');return;}
        const data=await response.json();if(!response.ok)throw new Error(data.error);
        const aborted = new Promise<never>((_,reject)=>controller.signal.addEventListener('abort',()=>reject(new Error('The dashboard is taking too long to respond.')),{once:true}));
        await Promise.race([loadScript(instanceUrl),aborted]);
        await Promise.race([customElements.whenDefined('metabase-dashboard'),aborted]);
        if(cancelled || !container.current)return;
        const embed=document.createElement('metabase-dashboard');
        embed.setAttribute('token',data.jwt);embed.setAttribute('dashboard-id',String(id));
        embed.setAttribute('with-title','false');
        embed.className=`metabase-view metabase-${section} metabase-${role}`;
        container.current.replaceChildren(embed);setLoading(false);
      } catch(error) { if(!cancelled)setError(error instanceof Error ? error.message : 'Unable to load the dashboard.'); }
      finally { clearTimeout(timeout); }
    }
    void load();
    return () => {cancelled=true;controller.abort();clearTimeout(timeout);container.current?.replaceChildren();};
  },[id,role,publicUrl,run,section,startDate,endDate,department,attempt,search]);
  return <section className="embed-card" aria-label={section === 'tables' ? 'Attendance tables' : section === 'period' ? 'Attendance trend' : 'Daily attendance overview'}>
    {loading&&!error&&<div className="embed-loading" role="status"><span className="spinner"/><h2>Loading {section}</h2></div>}
    {error&&<div className="embed-error" role="alert"><h2>We couldn’t load the {section}</h2><p>{error}</p><button className="secondary-button" onClick={()=>setAttempt(attempt+1)}>Try again</button></div>}
    <div ref={container}/>
  </section>;
}

export function OperationalDashboard({ role, runs, publicUrl }: { role: Role; runs: TestRun[]; publicUrl: string }) {
  const [runKey,setRunKey] = useState(runs[0].key);
  const run = runs.find(item=>item.key===runKey)!;
  const [dailyDate,setDailyDate] = useState(run.startDate);
  const [draftDailyDate,setDraftDailyDate] = useState(run.startDate);
  const [dailyDepartment,setDailyDepartment] = useState('');
  const [draftDailyDepartment,setDraftDailyDepartment] = useState('');
  const [periodStart,setPeriodStart] = useState(periodStartFor('7D',run.endDate));
  const [periodEnd,setPeriodEnd] = useState(run.endDate);
  const [draftStart,setDraftStart] = useState(periodStartFor('7D',run.endDate));
  const [preset,setPreset] = useState<PeriodPreset | 'custom'>('7D');
  const [draftEnd,setDraftEnd] = useState(run.endDate);
  const [periodDepartment,setPeriodDepartment] = useState('');
  const [draftPeriodDepartment,setDraftPeriodDepartment] = useState('');
  const [draftSearch,setDraftSearch] = useState('');
  const [search,setSearch] = useState('');
  function chooseRun(key: string) {
    const next = runs.find(item=>item.key===key)!;
    setRunKey(key);setDailyDate(next.startDate);setDraftDailyDate(next.startDate);
    setPeriodStart(periodStartFor('7D',next.endDate));setPeriodEnd(next.endDate);setDraftStart(periodStartFor('7D',next.endDate));setDraftEnd(next.endDate);setPreset('7D');
    setSearch('');setDraftSearch('');setDailyDepartment('');setDraftDailyDepartment('');setPeriodDepartment('');setDraftPeriodDepartment('');
  }
  function submitDaily(event: FormEvent<HTMLFormElement>) { event.preventDefault();setDailyDate(draftDailyDate);setDailyDepartment(draftDailyDepartment); }
  function choosePreset(value: PeriodPreset) {
    const end=draftEnd||periodEnd;const start=periodStartFor(value,end);setPreset(value);setDraftStart(start);setDraftEnd(end);setPeriodStart(start);setPeriodEnd(end);
  }
  function submitPeriod(event: FormEvent<HTMLFormElement>) { event.preventDefault();const start=preset==='custom'?draftStart:periodStartFor(preset,draftEnd);if(start<=draftEnd){setDraftStart(start);setPeriodStart(start);setPeriodEnd(draftEnd);setPeriodDepartment(draftPeriodDepartment);} }
  function submitSearch(event: FormEvent<HTMLFormElement>) { event.preventDefault();setSearch(draftSearch.trim()); }
  return <>
    <div className="data-banner"><span className="banner-dot"/><div><strong>Test data · {run.label}</strong><span>{run.note}</span></div><span className="banner-tag">PREVIEW</span></div>
    <div className="report-controls"><label>Test run<select aria-label="Test run" value={runKey} onChange={event=>chooseRun(event.target.value)}>{runs.map(item=><option key={item.key} value={item.key}>{item.label}</option>)}</select></label></div>
    <section className="dashboard-surface" aria-label="Attendance dashboard">
      <div className="dashboard-surface-heading"><div><h2>Attendance overview</h2><p>Daily metrics and attendance trends</p></div><span className="daily-scope-label">Daily snapshot · {dailyDate}</span></div>
      <form onSubmit={submitDaily} className="report-controls daily-filters" aria-label="Daily attendance filters">
        <label>Reporting date<input type="date" required value={draftDailyDate} onChange={event=>setDraftDailyDate(event.target.value)}/></label>
        {role==='director'&&<DepartmentPicker key={`${runKey}-daily`} run={runKey} onChange={setDraftDailyDepartment}/>}
        <button className="search-button" type="submit">Apply daily filters</button>
      </form>
      <DashboardSection id={run[role].overview} role={role} publicUrl={publicUrl} run={runKey} section="overview" startDate={dailyDate} endDate={dailyDate} department={dailyDepartment}/>
      <div className="trend-panel">
        <div className="trend-heading"><div><h3 id="period-section-title">Attendance trend</h3><p>{periodStart} — {periodEnd}</p></div><div className="period-presets" role="group" aria-label="Trend period">{periodPresets.map(value=><button type="button" key={value} aria-pressed={preset===value} onClick={()=>choosePreset(value)}>{value}</button>)}<button type="button" aria-pressed={preset==='custom'} onClick={()=>setPreset('custom')}>Custom</button></div></div>
        <form onSubmit={submitPeriod} className="report-controls period-filters" aria-label="Attendance period filters">
          {preset==='custom'&&<label>Period start<input type="date" required value={draftStart} max={draftEnd} onChange={event=>setDraftStart(event.target.value)}/></label>}
          <label>Period end<input type="date" required value={draftEnd} min={preset==='custom'?draftStart:undefined} onChange={event=>setDraftEnd(event.target.value)}/></label>
          {role==='director'&&<DepartmentPicker key={`${runKey}-period`} run={runKey} onChange={setDraftPeriodDepartment}/>}
          <button className="search-button" type="submit">Apply period filters</button>
          <p className="filter-scope-note">Trend only. Daily cards and tables keep their reporting date.</p>
        </form>
        <DashboardSection id={run[role].period} role={role} publicUrl={publicUrl} run={runKey} section="period" startDate={periodStart} endDate={periodEnd} department={periodDepartment}/>
      </div>
      <div className="table-section" aria-label="Search attendance tables">
        <h3>{role==='director'?'Department attendance':'Employee attendance'}</h3>
        <form className="dashboard-search" onSubmit={submitSearch}>
          <label htmlFor="table-search">{role==='director'?'Find a department in the table':'Find an employee in the table'}</label>
          <div className="dashboard-search-controls"><input id="table-search" value={draftSearch} onChange={event=>setDraftSearch(event.target.value)} maxLength={100} placeholder={role==='director'?'Department name':'Employee name'} autoComplete="off"/><button className="search-button" type="submit">Search table</button>{search&&<button className="clear-search-button" type="button" onClick={()=>{setDraftSearch('');setSearch('');}}>Clear</button>}</div>
          <p>{search ? <>Table matching <strong>“{search}”</strong>. </> : null}Search applies only to this daily table.</p>
        </form>
        <DashboardSection id={run[role].tables} role={role} publicUrl={publicUrl} run={runKey} section="tables" startDate={dailyDate} endDate={dailyDate} department={dailyDepartment} search={search}/>
      </div>
    </section>
  </>;
}
