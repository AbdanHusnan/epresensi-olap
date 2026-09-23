// PLAYWRIGHT_MODULE may point to a temporary Playwright installation.
// No credentials, headers, guest tokens, or returned data rows are recorded.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const { performance } = require('node:perf_hooks');
const origin = process.env.BENCH_ORIGIN || 'http://127.0.0.1:3002';
const output = process.env.BENCH_OUTPUT || '/tmp/olap-dashboard-benchmark.json';
const runs = Number(process.env.BENCH_RUNS || 3);
const dashboards = [['overview','/',7],['attendance','/attendance',6],['departments','/departments',2],['lateness','/lateness-absence',5]];
(async () => {
 const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_PATH, args:['--no-sandbox']});
 const results = [];
 try {
 for (const [key,path,chartCount] of dashboards) {
  const context = await browser.newContext({viewport:{width:1440,height:1100}});
  for (let run=0;run<runs;run++) {
   const page=await context.newPage(); const records=[];const active=new Set();const metadata=new Map();const jobs=[];let lastFinished=0;
   page.on('request',req=>{if(req.url().includes('/api/')){active.add(req);metadata.set(req,{path:new URL(req.url()).pathname,method:req.method(),start:performance.now(),payload:req.url().includes('/chart/data')?req.postDataJSON():undefined});}});
   page.on('requestfinished',req=>{
    if(!metadata.has(req))return;active.delete(req);lastFinished=performance.now();
    const item=metadata.get(req);item.end=lastFinished;item.durationMs=item.end-item.start;records.push(item);
    jobs.push((async()=>{const res=await req.response();item.status=res.status();item.timing=req.timing();
     if(item.path.includes('/chart/data') && res.ok()) {const json=await res.json();item.queries=(json.result||[]).map(q=>({query:q.query,isCached:q.is_cached,cacheTimeout:q.cache_timeout,rows:q.rowcount,status:q.status,error:q.error,duration:q.duration,timing:q.timing}));}
    })().catch(e=>{item.parseError=e.message}));
   });
   page.on('requestfailed',req=>{active.delete(req);if(metadata.has(req))records.push({...metadata.get(req),failed:req.failure()?.errorText,end:performance.now()});});
   async function settle(start, expected) {
    const deadline=performance.now()+90000;
    while(performance.now()<deadline){
     const completed=records.filter(r=>r.start>=start&&r.path.includes('/chart/data')&&r.status===200);
     const frame=page.frames().find(f=>f.url().includes('/embedded/'));
     if(completed.length>=expected && active.size===0 && performance.now()-lastFinished>500 && frame){
      const state=await frame.evaluate(()=>({text:document.body.innerText,charts:document.querySelectorAll('.slice_container').length}));
      if(!/Waiting on database|Loading filter values|Something went wrong|Unexpected error/.test(state.text)) {
       await frame.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
       return {readyMs:performance.now()-start,lastChartMs:Math.max(...completed.map(r=>r.end))-start,charts:state.charts};
      }
     }
     await new Promise(r=>setTimeout(r,100));
    }
    throw Error(`Timeout waiting for charts: ${key}, requests=${records.length}, active=${active.size}`);
   }
   const start=performance.now();await page.goto(origin+path);const initial=await settle(start,chartCount);await Promise.all(jobs);
   const initialEnd=performance.now();
   const frame=page.frames().find(f=>f.url().includes('/embedded/'));
   let filter=null;
   if(key!=='departments') {
    await frame.getByRole('combobox').click();const option=frame.locator('.ant-select-item-option').first();await option.waitFor();const label=await option.innerText();await option.click();
    const filterStart=performance.now();await frame.getByRole('button',{name:'Apply filters',exact:true}).click();
    filter={label,...await settle(filterStart,chartCount),start:filterStart};await Promise.all(jobs);
   }
   const item={key,run:run+1,browserCache:run===0?'fresh context':'warm context',initial,filter,records:records.map(r=>({...r,start:r.start-start,end:r.end-start,phase:r.start<initialEnd?'initial':'filter'}))};
   results.push(item);fs.writeFileSync(output,JSON.stringify({measuredAt:new Date().toISOString(),origin,results},null,2));
   console.log(JSON.stringify({key,run:run+1,initial,filter}));await page.close();
  }
  await context.close();
 }
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
