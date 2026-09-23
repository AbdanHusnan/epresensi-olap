const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs');const {performance}=require('node:perf_hooks');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']});const context=await browser.newContext({viewport:{width:1440,height:1100}});const results=[];
try{
 for(let run=1;run<=3;run++){
  const page=await context.newPage();let start=0;let finished=[];let active=0;let last=0;
  page.on('request',r=>{if(start && r.url().includes('/chart/data'))active++});
  page.on('requestfinished',async r=>{if(start && r.url().includes('/chart/data')){active--;last=performance.now();finished.push({status:(await r.response()).status(),finishMs:last-start,durationMs:r.timing().responseEnd-r.timing().requestStart});}});
  await page.goto('http://127.0.0.1:3002/departments');await page.waitForTimeout(10000);
  const frame=page.frames().find(f=>f.url().includes('/embedded/'));
  await frame.getByText('2026-08-01 ≤ col < 2026-09-01',{exact:true}).click();
  await frame.locator('input[value="2026-08-01"]').fill('2026-08-03');
  await frame.locator('input[value="2026-09-01"]').fill('2026-08-04');
  await frame.locator('input[value="2026-08-04"]').press('Tab');
  await frame.getByRole('button',{name:/^apply$/i}).click();
  start=performance.now();await frame.getByRole('button',{name:'Apply filters',exact:true}).click();
  while(performance.now()-start<60000){
   if(finished.length>=2&&active===0&&performance.now()-last>500){
    const text=await frame.locator('body').innerText();
    if(!text.includes('Waiting on database')){
     const item={run,range:'2026-08-03 <= tanggal < 2026-08-04',readyMs:performance.now()-start,lastChartMs:last-start,requests:finished};results.push(item);console.log(JSON.stringify(item));break;
    }
   }
   await new Promise(r=>setTimeout(r,100));
  }
  if(results.length!==run)throw Error('Date filter did not settle');
  fs.writeFileSync(process.env.BENCH_OUTPUT || '/tmp/olap-dashboard-date-benchmark.json',JSON.stringify(results,null,2));await page.close();
 }
} finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
