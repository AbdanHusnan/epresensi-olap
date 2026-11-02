const {chromium} = require('/tmp/olap-dashboard-browser/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const env = Object.fromEntries(fs.readFileSync(path.join(__dirname, '../../.env.hybrid'), 'utf8').split('\n')
 .filter(line => line && !line.startsWith('#')).map(line => {const i=line.indexOf('=');return [line.slice(0,i),line.slice(i+1)];}));
const label = process.argv[2] || 'first';
const baseline = JSON.parse(fs.readFileSync(path.join(__dirname,'verification_first.json'),'utf8'));
(async()=>{
 const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
 const results=[];
 try {
  for(const role of ['director','manager']) {
   const ctx=await browser.newContext({viewport:{width:1600,height:1100}});
   const page=await ctx.newPage();
   const errors=[];
   page.on('pageerror',e=>errors.push(e.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]')));
   await page.goto('http://localhost:3100/login');
   await page.getByLabel('Username',{exact:true}).fill(role);
   await page.getByLabel('Password',{exact:true}).fill(env['DEMO_'+role.toUpperCase()+'_PASSWORD']);
   await page.getByRole('button',{name:'Sign in',exact:true}).click();
   await page.waitForURL('**/'+(role==='director'?'analytical':'operational'));
   if(!(await page.locator('body').innerText()).includes('2 November 2026'))throw new Error('Wrong website test date');
   let found=false;
   for(let i=0;i<160&&!found;i++) {
    for(const frame of page.frames()) {
     const text=await frame.locator('body').innerText().catch(()=>'');
     if(role==='director' && text.includes('Top 10 departments by first-shift lateness') && text.includes('Assessed: 69102'))found=true;
     if(role==='manager' && text.includes('Employee daily records') && text.includes('PROVISIONAL'))found=true;
    }
    if(!found) {
     await page.evaluate(()=>window.scrollBy(0,300));
     for(const frame of page.frames())if(frame!==page.mainFrame())await frame.evaluate(()=>window.scrollBy(0,300)).catch(()=>{});
     await page.waitForTimeout(250);
    }
   }
   if(!found)throw new Error(role+' checkpoint did not render');
   if(errors.length)throw new Error(role+' browser errors: '+errors.join('; '));
   if(role==='director') {
    for(const frame of page.frames()) {
     const title=frame.getByText('Top 10 departments by first-shift lateness (%)',{exact:true});
     if(await title.count())await title.first().scrollIntoViewIfNeeded().catch(()=>{});
    }
   }
   await page.screenshot({path:path.join(__dirname,'browser_'+label+'_'+role+'.png'),fullPage:false});
   results.push({role,passed:true,date:'2026-11-02',pageErrors:errors});
   console.log(role,'browser checkpoint passed');
   await ctx.close();
  }
 } finally {await browser.close();}
 fs.writeFileSync(path.join(__dirname,'browser_'+label+'.json'),JSON.stringify({passed:true,date:'2026-11-02',firstCheckpointPopulation:baseline.results.population,results},null,2)+'\n');
})().catch(error=>{console.error(error.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]'));process.exit(1);});
