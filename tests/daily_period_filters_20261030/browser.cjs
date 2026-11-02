const {chromium}=require('/tmp/olap-dashboard-browser/node_modules/playwright');
const fs=require('fs');const path=require('path');const dir=__dirname;
const env=Object.fromEntries(fs.readFileSync(path.join(dir,'../../.env.hybrid'),'utf8').split('\n').filter(l=>l&&!l.startsWith('#')).map(l=>{const i=l.indexOf('=');return [l.slice(0,i),l.slice(i+1)]}));
const runs=JSON.parse(fs.readFileSync(path.join(dir,'../../hybrid-dashboard/lib/test-runs.json'),'utf8'));
const claims=t=>JSON.parse(Buffer.from(t.split('.')[1],'base64url').toString());
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
 try {
  for(const role of ['director','manager']) {
   const ctx=await browser.newContext({viewport:{width:1600,height:1100}});const page=await ctx.newPage();const errors=[];
   page.on('pageerror',e=>errors.push(e.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]')));
   await page.goto('http://localhost:3100/login');await page.getByLabel('Username',{exact:true}).fill(role);await page.getByLabel('Password',{exact:true}).fill(env['DEMO_'+role.toUpperCase()+'_PASSWORD']);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL('**/'+(role==='director'?'analytical':'operational'));
   const embeds=page.locator('metabase-dashboard');await page.waitForFunction(()=>document.querySelectorAll('metabase-dashboard').length===3);
   async function tokens(){await page.waitForFunction(()=>document.querySelectorAll('metabase-dashboard').length===3);return embeds.evaluateAll(items=>items.map(item=>item.getAttribute('token')));}
   async function waitChanged(index,previous){const id=runs[0][role][['overview','tables','period'][index]];await page.waitForFunction(({id,previous})=>{const token=document.querySelector(`metabase-dashboard[dashboard-id="${id}"]`)?.getAttribute('token');return !!token&&token!==previous;},{id,previous});}
   if((await embeds.nth(2).boundingBox()).height>900)throw new Error('Period embed has excessive fixed height');let initial=await tokens();if(claims(initial[0]).params.start_date!==claims(initial[0]).params.end_date)throw new Error('Daily scope has multiple dates');
   await page.getByLabel('Period start',{exact:true}).fill('2026-10-31');await page.getByRole('button',{name:'Apply period filters',exact:true}).click();await waitChanged(2,initial[2]);
   let after=await tokens();if(after[0]!==initial[0]||after[1]!==initial[1])throw new Error('Period filter refreshed daily embeds');if(claims(after[2]).params.start_date!=='2026-10-31')throw new Error('Period start not applied');
   await page.getByLabel('Reporting date',{exact:true}).fill('2026-10-31');await page.getByRole('button',{name:'Apply daily filters',exact:true}).click();await waitChanged(0,after[0]);
   let changedDaily=await tokens();if(changedDaily[2]!==after[2])throw new Error('Daily filter refreshed period embed');if(claims(changedDaily[0]).params.start_date!=='2026-10-31'||claims(changedDaily[0]).params.end_date!=='2026-10-31')throw new Error('Daily date not applied');
   await page.getByLabel('Reporting date',{exact:true}).fill('2026-10-30');await page.getByRole('button',{name:'Apply daily filters',exact:true}).click();await waitChanged(0,changedDaily[0]);
   await page.getByLabel('Period start',{exact:true}).fill('2026-10-30');await page.getByRole('button',{name:'Apply period filters',exact:true}).click();await waitChanged(2,after[2]);
   let selectedName=null;
   if(role==='director'){
    const daily=page.getByRole('form',{name:'Daily attendance filters'});const picker=daily.getByRole('combobox');await picker.fill('TATA USAHA');const option=daily.getByRole('option').first();await option.waitFor();selectedName=await option.locator('span').innerText();const selectedId=(await option.locator('small').innerText()).replace('ID ','');await option.click();let before=await tokens();await daily.getByRole('button',{name:'Apply daily filters',exact:true}).click();await waitChanged(0,before[0]);let scoped=await tokens();if(String(claims(scoped[0]).params.department)!==selectedId||String(claims(scoped[1]).params.department)!==selectedId)throw new Error('Department name did not scope daily cards/tables');if(scoped[2]!==before[2])throw new Error('Daily department changed the period');
    await page.locator('.daily-filters').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(dir,'department_name.png')});await daily.getByRole('button',{name:'Clear department',exact:true}).click();await daily.getByRole('button',{name:'Apply daily filters',exact:true}).click();await waitChanged(0,scoped[0]);
   }
   const beforeSearch=await tokens();await page.getByLabel('Find an employee or department in the tables',{exact:true}).fill('NO_MATCH_8939');await page.getByRole('button',{name:'Search tables',exact:true}).click();await waitChanged(1,beforeSearch[1]);const searched=await tokens();if(searched[0]!==beforeSearch[0]||searched[2]!==beforeSearch[2])throw new Error('Table search affected another section');
   await page.getByRole('button',{name:'Clear',exact:true}).click();
   // Wait for actual embedded charts, beyond successful token issuance.
   let rendered=false;
   for(let i=0;i<120&&!rendered;i++) {let texts=[];for(const frame of page.frames())if(frame!==page.mainFrame())texts.push(await frame.locator('body').innerText().catch(()=>''));rendered=texts.some(t=>t.includes('Pegawai Aktif'))&&texts.some(t=>t.includes('Employee daily records'))&&texts.some(t=>t.includes('Daily attendance trend'));if(!rendered)await page.waitForTimeout(500);}
   if(!rendered)throw new Error('One section failed to render');
   await page.locator('.daily-filters').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(dir,role+'_daily.png')});await page.locator('#period-section-title').scrollIntoViewIfNeeded();await page.waitForTimeout(500);await page.screenshot({path:path.join(dir,role+'_period.png')});
   await page.setViewportSize({width:390,height:844});await page.waitForTimeout(1500);if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw new Error('Mobile horizontal overflow');await page.locator('.daily-filters').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(dir,role+'_mobile.png')});
   for(const run of runs.slice(1)){await page.getByLabel('Test run',{exact:true}).selectOption(run.key);await page.waitForFunction(id=>document.querySelectorAll('metabase-dashboard').length===3&&document.querySelector('metabase-dashboard')?.getAttribute('dashboard-id')===String(id),run[role].overview);const state=await tokens();if(claims(state[0]).params.start_date!==run.startDate||claims(state[0]).params.end_date!==run.startDate)throw new Error('Run switching broke daily date');}
   if(errors.length)throw new Error(errors.join('; '));results.push({role,passed:true,dailyAndPeriodIndependent:true,tableSearchIsolated:true,selectedDepartmentName:selectedName,mobileOverflow:false,pageErrors:errors});console.log(role,'browser PASS');await ctx.close();
  }
 } finally {await browser.close();}
 fs.writeFileSync(path.join(dir,'browser_verification.json'),JSON.stringify({passed:true,results},null,2)+'\n');
})().catch(e=>{console.error(e.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]'));process.exit(1)});
