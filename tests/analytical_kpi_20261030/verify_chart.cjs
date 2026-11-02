const { chromium } = require('/tmp/olap-dashboard-browser/node_modules/playwright');
const fs = require('fs');
const env = Object.fromEntries(fs.readFileSync('.env.hybrid', 'utf8').split('\n')
  .filter(line => line && !line.startsWith('#'))
  .map(line => { const index = line.indexOf('='); return [line.slice(0, index), line.slice(index + 1)]; }));

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });
    await page.goto('http://localhost:3100/login');
    await page.getByLabel('Username', { exact: true }).fill('director');
    await page.getByLabel('Password', { exact: true }).fill(env.DEMO_DIRECTOR_PASSWORD);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await page.waitForURL('**/analytical');
    let chart;
    for (let i = 0; i < 80 && !chart; i++) {
      for (const frame of page.frames()) {
        const candidate = frame.getByTestId('row-chart-container');
        if (await candidate.count()) { chart = candidate.first(); break; }
      }
      if (!chart) {
        await page.evaluate(() => window.scrollBy(0, 250));
        await page.waitForTimeout(250);
      }
    }
    if (!chart || !await chart.isVisible()) throw new Error('Horizontal chart was not visible');
    const label = await chart.innerText();
    if (!label.includes('100')) throw new Error('Expected percentage labels were not rendered');
    console.log('Analytical horizontal chart rendered with percentage labels.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message.replace(/eyJ[A-Za-z0-9_.-]+/g, '[token]')); process.exit(1); });
