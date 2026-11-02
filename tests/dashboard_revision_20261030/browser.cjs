const { chromium } = require('/tmp/olap-dashboard-browser/node_modules/playwright');
const fs=require('fs');const path=require('path');const out=__dirname;
const env=Object.fromEntries(fs.readFileSync(path.join(out,'../../.env.hybrid'),'utf8').split('\n').filter(l=>l&&!l.startsWith('#')).map(l=>{const i=l.indexOf('=');return [l.slice(0,i),l.slice(i+1)]}));
const runs=JSON.parse(fs.readFileSync(path.join(out,'../../hybrid-dashboard/lib/test-runs.json'),'utf8'));
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const results=[];
 try {
  for(const role of ['director','manager']) {
   const ctx=await browser.newContext({viewport:{width:1600,height:1100}});const page=await ctx.newPage();const errors=[];
   page.on('pageerror',e=>errors.push(e.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]')));
   await page.goto('http://localhost:3100/login');await page.getByLabel('Username',{exact:true}).fill(role);await page.getByLabel('Password',{exact:true}).fill(env['DEMO_'+role.toUpperCase()+'_PASSWORD']);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL('**/'+(role==='director'?'analytical':'operational'));
   async function waitForCards() {
    await page.waitForFunction(()=>document.querySelectorAll('metabase-dashboard').length===2);
    let found=false;
    for(let i=0;i<120&&!found;i++) {
     let texts=[];for(const f of page.frames())if(f!==page.mainFrame())texts.push(await f.locator('body').innerText().catch(()=>''));
     found=texts.some(t=>t.includes('Daily attendance trend'))&&texts.some(t=>t.includes('Employee daily records'));
     if(!found)await page.waitForTimeout(500);
    }
    if(!found)throw new Error('Embedded overview/detail tables failed to render');
   }
   await waitForCards();
   await page.locator('.report-controls').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,role+'_overview.png')});
   if(role==='director')for(const f of page.frames()) {
    const title=f.getByText('Top 10 departments · first-shift lateness',{exact:true});
    if(await title.count()){await title.first().scrollIntoViewIfNeeded();await page.waitForTimeout(500);await page.screenshot({path:path.join(out,'director_rankings.png')});}
   }
   const overview=page.locator('metabase-dashboard').first();const before=await overview.getAttribute('token');
   await page.getByLabel('Find an employee or department in the tables',{exact:true}).fill('ZZZ_NO_MATCH_7be298');await page.getByRole('button',{name:'Search tables',exact:true}).click();
   await page.waitForTimeout(2000);if(await overview.getAttribute('token')!==before)throw new Error('Search refreshed the overview');
   await page.locator('.table-section').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,role+'_table_search.png')});
   await page.getByRole('button',{name:'Clear',exact:true}).click();
   for(const run of runs.slice(1)) {await page.getByLabel('Test run',{exact:true}).selectOption(run.key);await waitForCards();if(!(await page.locator('.data-banner').innerText()).includes(run.label))throw new Error('Wrong run banner');}
   await page.getByLabel('Test run',{exact:true}).selectOption(runs[0].key);await waitForCards();
   await page.setViewportSize({width:390,height:844});await page.waitForTimeout(500);
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);if(overflow)throw new Error('Mobile page overflows');
   await page.locator('.report-controls').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,role+'_mobile.png')});
   if(errors.length)throw new Error('Browser errors: '+errors.join('; '));
   results.push({role,passed:true,runs:runs.map(r=>r.key),searchDidNotRefreshOverview:true,mobileOverflow:false,pageErrors:errors});console.log(role,'browser PASS');await ctx.close();
  }
 } finally {await browser.close();}
 fs.writeFileSync(path.join(out,'browser_verification.json'),JSON.stringify({passed:true,results},null,2)+'\n');
})().catch(e=>{console.error(e.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]'));process.exit(1)});
