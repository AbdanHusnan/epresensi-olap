const { chromium } = require('/tmp/olap-dashboard-browser/node_modules/playwright');
const fs = require('fs');
const env = Object.fromEntries(fs.readFileSync('.env.hybrid', 'utf8').split('\n')
  .filter(line => line && !line.startsWith('#'))
  .map(line => { const i = line.indexOf('='); return [line.slice(0, i), line.slice(i + 1)]; }));
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
    await page.goto('http://localhost:3100/login');
    await page.getByLabel('Username', { exact: true }).fill('director');
    await page.getByLabel('Password', { exact: true }).fill(env.DEMO_DIRECTOR_PASSWORD);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await page.waitForURL('**/analytical');
    let found = false;
    for (let i = 0; i < 100 && !found; i++) {
      for (const frame of page.frames()) {
        const text = await frame.locator('body').innerText().catch(() => '');
        if (text.includes('Top 10 departments by first-shift lateness') && text.includes('Pending or unknown')) {
          found = true; break;
        }
      }
      if (!found) {
        await page.evaluate(() => window.scrollBy(0, 300));
        for (const frame of page.frames()) if (frame !== page.mainFrame())
          await frame.evaluate(() => window.scrollBy(0, 300)).catch(() => {});
        await page.waitForTimeout(250);
      }
    }
    if (!found) throw new Error('Lateness card or assessment coverage did not render');
    console.log('PASS: analytical lateness card and coverage rendered');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message.replace(/eyJ[A-Za-z0-9_.-]+/g, '[token]')); process.exit(1); });
