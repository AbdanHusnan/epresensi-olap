const {chromium}=require('/tmp/olap-dashboard-browser/node_modules/playwright');
const fs=require('fs');const path=require('path');const dir=__dirname;
const env=Object.fromEntries(fs.readFileSync(path.join(dir,'../../.env.hybrid'),'utf8').split('\n').filter(l=>l&&!l.startsWith('#')).map(l=>{const i=l.indexOf('=');return[l.slice(0,i),l.slice(i+1)]}));
const runs=JSON.parse(fs.readFileSync(path.join(dir,'../../hybrid-dashboard/lib/test-runs.json'),'utf8'));
const claims=t=>JSON.parse(Buffer.from(t.split('.')[1],'base64url').toString());
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
 try {
  for(const role of ['director','manager']){
   const ctx=await browser.newContext({viewport:{width:1600,height:1100}});const page=await ctx.newPage();const errors=[];
   page.on('pageerror',e=>errors.push(e.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]')));
   await page.goto('http://localhost:3100/login');await page.getByLabel('Username',{exact:true}).fill(role);await page.getByLabel('Password',{exact:true}).fill(env['DEMO_'+role.toUpperCase()+'_PASSWORD']);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL('**/'+(role==='director'?'analytical':'operational'));
   const ids=runs[0][role];
   async function state(){await page.waitForFunction(()=>document.querySelectorAll('.dashboard-surface metabase-dashboard').length===3);let out={};for(const section of ['overview','period','tables'])out[section]=await page.locator(`metabase-dashboard[dashboard-id="${ids[section]}"]`).getAttribute('token');return out;}
   async function changed(section,previous){await page.waitForFunction(({id,previous})=>{const token=document.querySelector(`metabase-dashboard[dashboard-id="${id}"]`)?.getAttribute('token');return !!token&&token!==previous;},{id:ids[section],previous});}
   let initial=await state();if(await page.locator('.dashboard-surface').count()!==1||await page.locator('.section-number').count())throw new Error('Layout is still split into numbered containers');
   if(claims(initial.overview).params.start_date!=='2026-10-30'||claims(initial.overview).params.end_date!=='2026-10-30')throw new Error('Daily scope incorrect');
   const presetResults=[];
   for(const [preset,start] of [['3D','2026-10-29'],['1M','2026-10-01'],['3M','2026-08-01'],['6M','2026-05-01'],['1Y','2025-11-01'],['7D','2026-10-25']]){
    const before=await state();await page.getByRole('button',{name:preset,exact:true}).click();await changed('period',before.period);const after=await state();if(claims(after.period).params.start_date!==start||claims(after.period).params.end_date!=='2026-10-31')throw new Error('Wrong preset: '+preset);if(after.overview!==before.overview||after.tables!==before.tables)throw new Error('Preset refreshed daily metrics');presetResults.push(preset);
   }
   const beforeCustom=await state();await page.getByRole('button',{name:'Custom',exact:true}).click();await page.getByLabel('Period start',{exact:true}).fill('2026-10-30');await page.getByRole('button',{name:'Apply period filters',exact:true}).click();await changed('period',beforeCustom.period);
   const beforeDaily=await state();await page.getByLabel('Reporting date',{exact:true}).fill('2026-10-31');await page.getByRole('button',{name:'Apply daily filters',exact:true}).click();await changed('overview',beforeDaily.overview);const dailyChanged=await state();if(dailyChanged.period!==beforeDaily.period)throw new Error('Daily date changed trend');await page.getByLabel('Reporting date',{exact:true}).fill('2026-10-30');await page.getByRole('button',{name:'Apply daily filters',exact:true}).click();await changed('overview',dailyChanged.overview);
   const beforeSearch=await state();await page.getByLabel(role==='director'?'Find a department in the table':'Find an employee in the table',{exact:true}).fill('NO_MATCH_8391');await page.getByRole('button',{name:'Search table',exact:true}).click();await changed('tables',beforeSearch.tables);const searched=await state();if(searched.overview!==beforeSearch.overview||searched.period!==beforeSearch.period)throw new Error('Table search refreshed charts');await page.getByRole('button',{name:'Clear',exact:true}).click();await changed('tables',searched.tables);
   let rendered=false;
   for(let i=0;i<100&&!rendered;i++){let text='';for(const frame of page.frames())if(frame!==page.mainFrame())text+='\n'+await frame.locator('body').innerText().catch(()=>'');if(role==='director'&&text.includes('Employee daily records'))throw new Error('Top management still sees employee records');rendered=text.includes('Pegawai Aktif')&&text.includes('Daily attendance trend')&&text.includes(role==='director'?'Department summary':'Employee daily records');if(!rendered)await page.waitForTimeout(400);}
   if(!rendered)throw new Error('Dashboard failed to render');
   await page.locator('.dashboard-surface-heading').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(dir,role+'_overview.png')});await page.locator('.trend-heading').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(dir,role+'_trend.png')});await page.locator('.table-section h3').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(dir,role+'_table.png')});
   await page.setViewportSize({width:390,height:844});await page.waitForTimeout(1200);if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw new Error('Mobile overflow');await page.locator('.trend-heading').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(dir,role+'_mobile.png')});
   if(errors.length)throw new Error(errors.join('; '));results.push({role,passed:true,unifiedContainer:true,presets:presetResults,dailyAndTrendIndependent:true,roleAppropriateTable:true,tableSearchIsolated:true,mobileOverflow:false,pageErrors:errors});console.log(role,'browser PASS');await ctx.close();
  }
 }finally{await browser.close();}
 fs.writeFileSync(path.join(dir,'browser_verification.json'),JSON.stringify({passed:true,results},null,2)+'\n');
})().catch(e=>{console.error(e.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]'));process.exit(1)});
