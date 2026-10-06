/* Measure what actually overflows the viewport on a page.
 *
 * Reading the markup does not find horizontal overflow - you have to lay the
 * page out and ask which box is wider than the screen. Run with node:
 *
 *   node scripts/measure.mjs                     # every page, every viewport
 *   node scripts/measure.mjs --vp 390 home
 *   node scripts/measure.mjs --console home     # console errors only
 */

import puppeteer from 'puppeteer-core';
import { existsSync } from 'node:fs';

const BASE = 'http://127.0.0.1:8000';

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

/* Everything that reports a problem. run() executes in the page, so anything
 * it returns has to be JSON-serialisable. */
function auditPage() {
  const doc = document.documentElement;
  const viewport = doc.clientWidth;

  // Which boxes stick out past the right edge.
  const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    // 1px of slack: sub-pixel rounding produces phantom overflow.
    if (rect.right > viewport + 1) {
      const style = getComputedStyle(el);
      offenders.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className || '').toString().slice(0, 90),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
        // Only report it if this element, not an ancestor, is the cause.
        overflowSelf:
          style.overflowX === 'visible' || style.overflowX === 'clip',
      });
    }
  }

  // Keep the innermost few: an offender's parent is usually also an offender,
  // and the parent is not the cause.
  const minimal = offenders.filter(
    (o, i) =>
      !offenders.some(
        (other, j) =>
          j !== i &&
          other.width < o.width &&
          other.width > 0 &&
          other.right >= o.right - 1
      )
  );

  // Tap targets under 44px, the WCAG 2.2 minimum for pointer input.
  const small = [];
  for (const el of document.querySelectorAll('a, button, input, select, [role="button"]')) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    if (getComputedStyle(el).display === 'inline') continue;
    if (rect.height < 44 || rect.width < 44) {
      small.push({
        tag: el.tagName.toLowerCase(),
        text: (el.textContent || '').trim().slice(0, 40),
        w: Math.round(rect.width),
        h: Math.round(rect.height),
      });
    }
  }

  // Images without alt text.
  const noAlt = [...document.querySelectorAll('img')]
    .filter((i) => !i.hasAttribute('alt'))
    .map((i) => (i.getAttribute('src') || '').slice(-50));

  // Heading order: a jump from h2 to h4 skips a level for screen readers.
  const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(
    (h) => Number(h.tagName[1])
  );
  const skips = [];
  for (let i = 1; i < headings.length; i += 1) {
    if (headings[i] - headings[i - 1] > 1) {
      skips.push(`${headings[i - 1]} to ${headings[i]}`);
    }
  }

  return {
    viewport,
    scrollWidth: doc.scrollWidth,
    overflows: doc.scrollWidth > viewport + 1,
    offenders: minimal.slice(0, 8),
    h1Count: document.querySelectorAll('h1').length,
    smallTargets: small.slice(0, 6),
    smallTargetCount: small.length,
    noAlt,
    headingSkips: skips,
    title: document.title,
    description:
      document.querySelector('meta[name="description"]')?.content || null,
    canonical: document.querySelector('link[rel="canonical"]')?.href || null,
    lang: doc.lang,
    jsonLd: document.querySelectorAll('script[type="application/ld+json"]').length,
  };
}

async function main() {
  const args = process.argv.slice(2);
  // "--vp 390" and "--vp=390" both work, and the value is consumed rather
  // than left behind to be mistaken for a page name.
  const vpIndex = args.findIndex((a) => a === '--vp' || a.startsWith('--vp='));
  let vpArg = null;
  if (vpIndex !== -1) {
    const raw = args[vpIndex].includes('=')
      ? args[vpIndex].split('=')[1]
      : args[vpIndex + 1];
    vpArg = Number(raw);
    args.splice(vpIndex, raw === args[vpIndex + 1] ? 2 : 1);
  }
  const consoleOnly = args.includes('--console');
  const names = args.filter((a) => !a.startsWith('--'));
  const pages = names.length ? names : Object.keys(PAGES);
  const viewports = vpArg ? { [`${vpArg}`]: vpArg } : VIEWPORTS;

  const browser = await puppeteer.launch({
    executablePath: chromePath(),
    headless: true,
    args: ['--no-sandbox', '--disable-gpu'],
  });

  let problems = 0;

  for (const name of pages) {
    if (!(name in PAGES)) {
      console.log(`unknown page ${name}`);
      continue;
    }
    for (const [label, width] of Object.entries(viewports)) {
      const page = await browser.newPage();
      await page.setViewport({ width, height: 1000 });

      const consoleErrors = [];
      page.on('console', (m) => {
        if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 160));
      });
      page.on('pageerror', (e) => consoleErrors.push(`UNCAUGHT ${e.message}`.slice(0, 160)));
      const failedRequests = [];
      page.on('requestfailed', (r) =>
        failedRequests.push(`${r.failure()?.errorText} ${r.url().slice(0, 80)}`)
      );

      /* Subresource failures only.
       *
       * Chrome logs the *main document's own* 404 as a console error
       * ("Failed to load resource: the server responded with a status of
       * 404"), so visiting the 404 page looks like a broken asset when
       * nothing is broken at all. Checking responses instead of console text
       * distinguishes the two: the document's status is expected, a
       * stylesheet or script 404 is not. */
      const badSubresources = [];
      page.on('response', (res) => {
        const status = res.status();
        if (status < 400) return;
        const type = res.request().resourceType();
        if (type === 'document' && res.url().replace(/\/$/, '') === `${BASE}${PAGES[name]}`.replace(/\/$/, '')) {
          return; // the page itself, which is expected to 404
        }
        badSubresources.push(`${status} ${type} ${res.url().slice(0, 90)}`);
      });

      await page.goto(`${BASE}${PAGES[name]}`, { waitUntil: 'networkidle2', timeout: 45000 });
      // Let the Tailwind CDN compile and JS settle.
      await new Promise((r) => setTimeout(r, 1200));

      const result = await page.evaluate(auditPage);

      const flags = [];
      if (result.overflows) flags.push(`OVERFLOW ${result.scrollWidth}>${result.viewport}`);
      if (result.h1Count !== 1) flags.push(`h1=${result.h1Count}`);
      if (result.smallTargetCount) flags.push(`small-tap=${result.smallTargetCount}`);
      if (result.noAlt.length) flags.push(`no-alt=${result.noAlt.length}`);
      if (result.headingSkips.length) flags.push(`heading-skips=${result.headingSkips.join(',')}`);
      if (!result.description) flags.push('no-meta-description');
      if (!result.canonical) flags.push('no-canonical');
      if (!result.lang) flags.push('no-lang');
      if (consoleErrors.length) flags.push(`console=${consoleErrors.length}`);
      if (badSubresources.length) flags.push(`bad-asset=${badSubresources.length}`);
      if (failedRequests.length) flags.push(`failed-req=${failedRequests.length}`);

      if (flags.length) problems += 1;
      const mark = flags.length ? '!' : ' ';
      console.log(`${mark} ${name.padEnd(16)} ${label.padEnd(8)} ${flags.join('  ') || 'clean'}`);

      if (flags.length || consoleOnly) {
        for (const o of result.offenders)
          console.log(`     overflow: <${o.tag}> w=${o.width} right=${o.right} ${o.cls}`);
        for (const t of result.smallTargets.slice(0, 3))
          console.log(`     small tap: <${t.tag}> ${t.w}x${t.h} "${t.text}"`);
        for (const c of consoleErrors.slice(0, 3)) console.log(`     console: ${c}`);
        for (const f of failedRequests.slice(0, 3)) console.log(`     request: ${f}`);
        for (const b of badSubresources.slice(0, 3)) console.log(`     asset: ${b}`);
      }

      await page.close();
    }
  }

  await browser.close();
  console.log(`\n${problems} page/viewport combinations with findings`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});