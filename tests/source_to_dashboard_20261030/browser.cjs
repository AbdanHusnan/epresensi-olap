const {chromium}=require('/tmp/olap-dashboard-browser/node_modules/playwright');
const fs=require('fs');const path=require('path');const OUT=__dirname;
const env=Object.fromEntries(fs.readFileSync(path.join(OUT,'../../.env.hybrid'),'utf8').split('\n').filter(x=>x&&!x.startsWith('#')).map(x=>{const i=x.indexOf('=');return[x.slice(0,i),x.slice(i+1)]}));
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
for(const mobile of [false,true])for(const role of ['director','manager']){
 const ctx=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1600,height:1100}});const p=await ctx.newPage();let started;const responses=[];const errors=[];
 p.on('pageerror',e=>errors.push(e.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]')));
 p.on('response',async r=>{if(/\/api\/embed\/dashboard\/.*\/dashcard\/\d+\/card\/\d+/.test(r.url())){let d;try{d=await r.json()}catch{}responses.push({status:r.status(),queryStatus:d?.status,seconds:(Date.now()-started)/1000,rows:d?.data?.rows?.length});}});
 await p.goto('http://localhost:3100/login');await p.getByLabel('Username',{exact:true}).fill(role);await p.getByLabel('Password',{exact:true}).fill(env['DEMO_'+role.toUpperCase()+'_PASSWORD']);started=Date.now();
 await p.getByRole('button',{name:'Sign in',exact:true}).click();await p.waitForURL('**/'+(role==='director'?'analytical':'operational'),{timeout:30000});const shellSeconds=(Date.now()-started)/1000;
 // Guest embed may lazy-load offscreen cards: scroll through the page to exercise all cards.
 for(let i=0;i<90&&responses.length<9;i++){
   await p.evaluate(()=>window.scrollBy(0,500));
   for(const f of p.frames())if(f!==p.mainFrame())await f.evaluate(()=>window.scrollBy(0,500)).catch(()=>{});
   await p.waitForTimeout(250);
 }
 await p.waitForTimeout(300);
 const frames=[];for(const f of p.frames()){try{frames.push(await f.locator('body').innerText())}catch{}}
 const text=frames.join('\n');const refs=JSON.parse(fs.readFileSync(path.join(OUT,'source_daily_http.json'),'utf8')).references;const expected=Number(refs[role][0]).toLocaleString('en-US');if(!text.includes(expected)||!text.includes('PROVISIONAL'))throw new Error('Rendered KPI/status missing');const renderedSeconds=(Date.now()-started)/1000;await p.evaluate(()=>window.scrollTo(0,0));for(const f of p.frames())if(f!==p.mainFrame())await f.evaluate(()=>window.scrollTo(0,0)).catch(()=>{});await p.waitForTimeout(700);const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 await p.screenshot({path:path.join(OUT,`browser-${role}-${mobile?'mobile':'desktop'}.png`),fullPage:false});
 results.push({role,mobile,shellSeconds,renderedSeconds,allChartsSeconds:responses.length>=9?Math.max(...responses.map(r=>r.seconds)):null,chartResponses:responses,renderedText:text,overflow,pageErrors:errors});
 console.log(role,mobile?'mobile':'desktop',responses.length,'charts',results.at(-1).allChartsSeconds,'seconds','overflow',overflow);
 await ctx.close();
}
await browser.close();fs.writeFileSync(path.join(OUT,'browser.json'),JSON.stringify(results,null,2)+'\n');
if(results.some(r=>r.chartResponses.length<9||r.chartResponses.some(c=>(c.status<200||c.status>=300)||c.queryStatus!=='completed')||r.overflow||r.pageErrors.length))process.exitCode=1;
})().catch(e=>{console.error(e.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]'));process.exit(1)});
