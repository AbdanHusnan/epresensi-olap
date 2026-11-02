const {chromium}=require('/tmp/olap-dashboard-browser/node_modules/playwright');
const fs=require('fs');const assert=require('assert');
const sourceOrigin=process.env.UI_SOURCE_ORIGIN;
const output=process.env.UI_ARTIFACT_DIR || '/tmp';
const env=Object.fromEntries(fs.readFileSync('/home/piramida/OLAP/.env.hybrid','utf8').split('\n').filter(x=>x&&!x.startsWith('#')).map(x=>{const i=x.indexOf('=');return[x.slice(0,i),x.slice(i+1)]}));
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-features=LocalNetworkAccessChecks,LocalNetworkAccessChecksWebSockets']});
 const context=await browser.newContext({permissions:['local-network-access']});
 // Keep the existing allowed website origin; proxy only this test browser to the new dev server.
 if(sourceOrigin) await context.route('http://localhost:3100/**',async route=>{
  const request=route.request();
  const response=await route.fetch({url:request.url().replace('http://localhost:3100',sourceOrigin),headers:{...request.headers(),'x-forwarded-host':'localhost:3100'},maxRedirects:0});
  await route.fulfill({response});
 });
 const page=await context.newPage();const errors=[];const tokens=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',async response=>{if(response.url().includes('/api/metabase-token')&&response.status()===200){const data=await response.json();tokens.push(JSON.parse(Buffer.from(data.jwt.split('.')[1],'base64url').toString()));}});
 const login=await context.request.post('http://localhost:3100/api/auth/login',{headers:{Origin:'http://localhost:3100'},data:{username:'director',password:env.DEMO_DIRECTOR_PASSWORD}});assert(login.ok());
 await page.goto('http://localhost:3100/analytical');
 await page.locator('.metabase-frame iframe').first().waitFor({timeout:60000});
 await page.waitForTimeout(12000);
 const results=[];
 for(const width of [1440,1024,768,390]){
  await page.setViewportSize({width,height:1000});await page.waitForTimeout(1800);
  for(const el of await page.locator('.metabase-frame').all()){await el.scrollIntoViewIfNeeded();await page.waitForTimeout(1500);}
  await page.locator('.overview-section').scrollIntoViewIfNeeded();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);assert(!overflow,`Page overflow at ${width}`);
  const frames=[];
  for(const frame of page.frames().slice(1)){
   frames.push(await frame.evaluate(()=>({text:document.body.innerText.slice(0,1800),height:document.documentElement.scrollHeight,bodyHeight:document.body.scrollHeight,viewport:window.innerHeight,cards:[...document.querySelectorAll('[data-testid="dashcard"]')].map(x=>({top:x.getBoundingClientRect().top,bottom:x.getBoundingClientRect().bottom,left:x.getBoundingClientRect().left,right:x.getBoundingClientRect().right}))})));
  }
  assert(frames.length===3,`Expected three Metabase frames at ${width}`);
  assert(frames[0].cards.length===6,`Expected six KPI cards at ${width}`);
  assert(Math.max(...frames[0].cards.map(card=>card.bottom)) < frames[0].viewport-64,`KPI cards clipped at ${width}`);
  await page.screenshot({path:`${output}/olap-analytical-${width}.png`,fullPage:true});await page.screenshot({path:`${output}/olap-analytical-viewport-${width}.png`});results.push({width,overflow,frames});
 }
 await page.setViewportSize({width:1440,height:1000});
 await page.getByLabel('Reporting date',{exact:true}).fill('2026-10-31');await page.getByRole('button',{name:'Apply',exact:true}).click();await page.waitForTimeout(1800);
 assert(new URL(page.url()).searchParams.get('date')==='2026-10-31');
 assert(tokens.some(t=>t.params.start_date==='2026-10-31'&&t.params.end_date==='2026-10-31'));
 await page.reload();await page.getByLabel('Reporting date',{exact:true}).waitFor();assert(await page.getByLabel('Reporting date',{exact:true}).inputValue()==='2026-10-31');
 await page.getByRole('button',{name:'Reset',exact:true}).click();assert(new URL(page.url()).searchParams.get('date')==='2026-10-30');
 await page.getByRole('button',{name:'1M',exact:true}).click();assert(new URL(page.url()).searchParams.get('preset')==='1M');
 await page.getByRole('button',{name:'Dismiss test run banner'}).click();assert(await page.locator('.test-run-banner').count()===0);
 fs.writeFileSync(`${output}/olap-ui-results.json`,JSON.stringify({results,errors,checks:['no page overflow','URL filter persistence','JWT uses reporting date','reset','banner dismiss','period preset URL','six KPI cards visible at every width']},null,2));
 console.log(JSON.stringify({widths:results.map(r=>({width:r.width,overflow:r.overflow,frames:r.frames.map(f=>({height:f.height,viewport:f.viewport,text:f.text.slice(0,150)}))})),errors,tokenRequests:tokens.length}));
 await browser.close();
})().catch(e=>{console.error(e.message.replace(/eyJ[A-Za-z0-9_.-]+/g,'[token]'));process.exit(1)});
