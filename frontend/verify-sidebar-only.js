const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const base = process.env.TUNNEL_URL || 'https://imported-called-lan-elevation.trycloudflare.com';
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const results = {};

  await page.goto(`${base}/dashboard`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  results.sidebarExists = await page.locator('aside').count();

  // Check for fixed bottom nav specifically - should be 0 since we removed it
  results.fixedBottomNav = await page.locator('nav[class*="bottom-0"]').count();

  await page.screenshot({ path: '/tmp/sidebar-only-dashboard.png', fullPage: true });

  console.log(JSON.stringify(results, null, 2));
  fs.writeFileSync('/tmp/sidebar-only-results.json', JSON.stringify(results, null, 2));

  await browser.close();
})();
