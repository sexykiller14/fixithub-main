/* Screenshot public pages at three viewports.
 *
 * Not a test - a tool for looking at what a visitor actually sees.
 *
 *   node scripts/shoot.mjs                  # every page, every viewport
 *   node scripts/shoot.mjs home articles    # named pages only
 *   node scripts/shoot.mjs --vp mobile      # one viewport
 *
 * Uses puppeteer and waits for the network to settle rather than Chrome's
 * --virtual-time-budget. That flag fast-forwards timers, which captures the
 * layout *before* the Tailwind CDN has compiled: it renders the desktop
 * layout into a mobile-sized window and looks like a horizontal overflow that
 * does not exist. Measured with waitUntil networkidle2, scrollWidth equals
 * clientWidth at every width.
 *
 * Output lands in .screenshots/, which is gitignored.
 */

import puppeteer from 'puppeteer-core';
import { existsSync, mkdirSync, rmSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE = 'http://127.0.0.1:8000';
const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, '.screenshots');

const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
];

const PAGES = {
  home: '/',
  articles: '/articles',
  article: '/articles/fix-no-internet-windows',
  category: '/category/network',
  search: '/search?q=wifi',
  bsod: '/bsod',
  'bsod-detail': '/bsod/MEMORY_MANAGEMENT',
  'bsod-analyze': '/bsod/analyze',
  wizards: '/wizards',
  'wizard-step': '/wizards/no-internet',
  tools: '/tools',
  'tool-dns': '/tools/dns',
  'tool-port': '/tools/port',
  'tool-status': '/tools/status',
  'tool-latency': '/tools/latency',
  'tool-ip': '/tools/ip',
  drivers: '/drivers',
  'driver-detail': '/drivers/realtek',
  hardware: '/hardware',
  'hardware-topic': '/hardware/ram',
  scripts: '/scripts',
  'script-detail': '/scripts/network-reset',
  apps: '/apps',
  about: '/about',
  privacy: '/privacy',
  login: '/login',
  signup: '/signup',
  '404': '/this-page-does-not-exist',
};

const VIEWPORTS = { mobile: 390, tablet: 768, desktop: 1280 };

function chromePath() {
  for (const p of CHROME_CANDIDATES) if (existsSync(p)) return p;
  throw new Error('No Chrome or Edge found');
}

async function main() {
  const args = process.argv.slice(2);
  const vpIndex = args.findIndex((a) => a === '--vp' || a.startsWith('--vp='));
  let vpOnly = null;
  if (vpIndex !== -1) {
    vpOnly = args[vpIndex].includes('=')
      ? args[vpIndex].split('=')[1]
      : args[vpIndex + 1];
    args.splice(vpIndex, args[vpIndex].includes('=') ? 1 : 2);
  }

  const names = args.filter((a) => !a.startsWith('--'));
  const pages = names.length ? names : Object.keys(PAGES);
  const viewports = vpOnly ? { [vpOnly]: VIEWPORTS[vpOnly] } : VIEWPORTS;

  mkdirSync(OUT, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: chromePath(),
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars'],
  });

  console.log(`chrome: ${chromePath()}`);
  console.log(`output: ${OUT}`);

  let count = 0;
  for (const name of pages) {
    if (!(name in PAGES)) {
      console.log(`unknown page '${name}' - known: ${Object.keys(PAGES).join(', ')}`);
      continue;
    }
    for (const [label, width] of Object.entries(viewports)) {
      const page = await browser.newPage();
      await page.setViewport({ width, height: 1000 });
      await page.goto(`${BASE}${PAGES[name]}`, { waitUntil: 'networkidle2', timeout: 45000 });
      // The Tailwind CDN compiles in a script that runs after load.
      await new Promise((r) => setTimeout(r, 1200));

      const target = join(OUT, `${name}-${label}.png`);
      rmSync(target, { force: true });
      await page.screenshot({ path: target, fullPage: true });

      const size = existsSync(target) ? statSync(target).size : 0;
      count += 1;
      console.log(`  ${name.padEnd(16)} ${label.padEnd(8)} ${size.toLocaleString().padStart(9)} bytes`);
      await page.close();
    }
  }

  await browser.close();
  console.log(`\n${count} screenshots in ${OUT}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});