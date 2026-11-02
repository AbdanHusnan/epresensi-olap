'use client';
import { useEffect, useRef, useState } from 'react';
import type { Role } from '../lib/auth';

declare global { interface Window { metabaseConfig?: { isGuest: boolean; instanceUrl: string; guestEmbedProviderUri: string; theme?: { preset: "light" }; }; } }
let scriptReady: Promise<void> | undefined;
function loadScript(instanceUrl: string): Promise<void> {
  if (scriptReady) return scriptReady;
  window.metabaseConfig = { isGuest: true, instanceUrl, guestEmbedProviderUri: '/api/metabase-token', theme: { preset: 'light' } };
  scriptReady = new Promise((resolve,reject) => {
    const script = document.createElement('script');
    script.src = `${instanceUrl}/app/embed.js`; script.async = true;
    script.onload = () => resolve();
    script.onerror = () => { script.remove(); scriptReady = undefined; reject(new Error('Unable to connect to the dashboard service.')); };
    document.head.appendChild(script);
  });
  return scriptReady;
}

export function MetabaseFrame({ id, role, publicUrl, run, section, startDate, endDate, department, search = '' }: { id: number; role: Role; publicUrl: string; run: string; section: 'overview' | 'tables' | 'period'; startDate: string; endDate: string; department: string; search?: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState('');
  const [attempt,setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const timeout = setTimeout(() => { controller.abort(); if (!cancelled) { setError('Layanan dashboard membutuhkan waktu terlalu lama untuk merespons.'); setLoading(false); } }, 45000);
    setLoading(true);setError('');
    async function load() {
      try {
        const host = new URL(window.location.origin);host.port='3101';
        const instanceUrl = publicUrl || host.origin;
        const response = await fetch('/api/metabase-token', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({entityType:'dashboard',entityId:id,run,section,startDate,endDate,department,search}), signal:controller.signal });
        if(response.status===401){window.location.assign('/login');return;}
        const data=await response.json();if(!response.ok)throw new Error(data.error);
        const aborted = new Promise<never>((_,reject)=>controller.signal.addEventListener('abort',()=>reject(new Error('Layanan dashboard membutuhkan waktu terlalu lama untuk merespons.')),{once:true}));
        await Promise.race([loadScript(instanceUrl),aborted]);
        await Promise.race([customElements.whenDefined('metabase-dashboard'),aborted]);
        if(cancelled || !container.current)return;
        const embed=document.createElement('metabase-dashboard');
        embed.setAttribute('token',data.jwt);embed.setAttribute('dashboard-id',String(id));
        embed.setAttribute('with-title','false');
        embed.setAttribute('with-downloads', section === 'tables' ? 'true' : 'false');
        embed.addEventListener('ready', () => { if (!cancelled) { clearTimeout(timeout); setLoading(false); } }, { once: true });
        embed.className=`metabase-view metabase-${section} metabase-${role}`;
        container.current.replaceChildren(embed);
      } catch(error) { if(!cancelled){clearTimeout(timeout);setLoading(false);setError(error instanceof Error ? error.message : 'Gagal memuat dashboard.');} }

    }
    void load();
    return () => {cancelled=true;controller.abort();clearTimeout(timeout);container.current?.replaceChildren();};
  },[id,role,publicUrl,run,section,startDate,endDate,department,attempt,search]);
  const skeletonCount = section === 'overview' ? 12 : section === 'period' ? 3 : 7;
  const sectionLabel = section === 'tables' ? 'Tabel kehadiran' : section === 'period' ? 'Tren kehadiran' : 'Ringkasan kehadiran';
  return <div className={`metabase-frame frame-${section}`} aria-busy={loading&&!error} aria-label={sectionLabel}>
    {loading&&!error&&<div className="embed-skeleton" role="status"><span className="sr-only">Memuat {sectionLabel}</span>{Array.from({length: skeletonCount}, (_, i)=><div key={i}/>)}</div>}
    {error&&<div className="embed-error" role="alert"><h2>Gagal memuat {sectionLabel}</h2><p>{error}</p><button className="secondary-button" onClick={()=>setAttempt(attempt+1)}>Coba lagi</button></div>}
    <div className="embed-mount" ref={container} style={{visibility: loading || error ? 'hidden' : 'visible'}}/>
  </div>;
}

