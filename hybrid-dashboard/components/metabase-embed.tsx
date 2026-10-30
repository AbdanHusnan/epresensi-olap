'use client';
import { useEffect, useRef, useState } from 'react';

declare global { interface Window { metabaseConfig?: { isGuest: boolean; instanceUrl: string; guestEmbedProviderUri: string; }; } }
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
export function MetabaseEmbed({ id, publicUrl }: { id: number; publicUrl: string }) {
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
        const response = await fetch('/api/metabase-token', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({entityType:'dashboard',entityId:id}), signal:controller.signal });
        if(response.status===401){window.location.assign('/login');return;}
        const data=await response.json();if(!response.ok)throw new Error(data.error);
        await Promise.race([loadScript(instanceUrl),new Promise((_,reject)=>controller.signal.addEventListener('abort',()=>reject(new Error('The dashboard is taking too long to respond.')),{once:true}))]);
        await Promise.race([customElements.whenDefined('metabase-dashboard'),new Promise((_,reject)=>controller.signal.addEventListener('abort',()=>reject(new Error('The dashboard component did not initialize.')),{once:true}))]);
        if(cancelled || !container.current)return;
        const embed=document.createElement('metabase-dashboard');
        embed.setAttribute('token',data.jwt);embed.setAttribute('dashboard-id',String(id));
        embed.setAttribute('with-title','false');
        embed.setAttribute('initial-parameters',JSON.stringify({start_date:'2026-10-30',end_date:'2026-10-30'}));
        embed.className='metabase-view';
        container.current.replaceChildren(embed);setLoading(false);
      } catch(error) { if(!cancelled)setError(error instanceof Error ? error.message : 'Unable to load the dashboard.'); }
      finally { clearTimeout(timeout); }
    }
    void load();
    return () => {cancelled=true;controller.abort();clearTimeout(timeout);container.current?.replaceChildren();};
  },[id,publicUrl,attempt]);
  return <section className="embed-card" aria-label="Attendance dashboard">
    {loading&&!error&&<div className="embed-loading" role="status"><span className="spinner"/><h2>Loading your dashboard</h2><p>Getting attendance insights ready.</p></div>}
    {error&&<div className="embed-error" role="alert"><span className="error-symbol">!</span><h2>We couldn’t load the dashboard</h2><p>{error}</p><button className="secondary-button" onClick={()=>setAttempt(attempt+1)}>Try again</button></div>}
    <div ref={container}/>
  </section>;
}
