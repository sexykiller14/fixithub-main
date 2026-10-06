/* Lighthouse scores for the public site.
 *
 *   node scripts/lighthouse.mjs                       # a representative set
 *   node scripts/lighthouse.mjs / /articles           # specific paths
 *   node scripts/lighthouse.mjs --label "before"      # tag the saved report
 *
 * Writes .lighthouse/<label>-<slug>.json and prints the four headline scores.
 * Mobile is the default because that is where most of the visitors are and
 * where the throttling does the most damage.
 */

import { launch } from 'chrome-launcher';
import lighthouse from 'lighthouse';
import { mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE = 'http://127.0.0.1:8000';
const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, '.lighthouse');

// A spread of page types rather than the whole site: the heaviest templates
// are the ones that decide the score.
const DEFAULT_PATHS = [
  '/',
  '/articles',
  '/articles/fix-no-internet-windows',
  '/bsod/MEMORY_MANAGEMENT',
  '/wizards',
  '/tools/dns',
  '/privacy',
];

const slug = (p) => (p === '/' ? 'home' : p.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, ''));

async function main() {
  const args = process.argv.slice(2);
  const labelIndex = args.findIndex((a) => a === '--label' || a.startsWith('--label='));
  let label = 'run';
  if (labelIndex !== -1) {
    label = args[labelIndex].includes('=')
      ? args[labelIndex].split('=')[1]
      : args[labelIndex + 1];
    args.splice(labelIndex, args[labelIndex].includes('=') ? 1 : 2);
  }
  const paths = args.filter((a) => a.startsWith('/'));
  const targets = paths.length ? paths : DEFAULT_PATHS;

  mkdirSync(OUT, { recursive: true });

  const chrome = await launch({
    chromePath:
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    chromeFlags: ['--headless=new', '--no-sandbox', '--disable-gpu'],
  });

  console.log(`label: ${label}`);
  const rows = [];

  for (const path of targets) {
    const result = await lighthouse(
      `${BASE}${path}`,
      { port: chrome.port, output: 'json', logLevel: 'error' },
      {
        extends: 'lighthouse:default',
        settings: { formFactor: 'mobile', screenEmulation: { mobile: true } },
      }
    );

    const lhr = result.lhr;
    const file = join(OUT, `${label}-${slug(path)}.json`);
    writeFileSync(file, JSON.stringify(lhr, null, 2));

    const row = {
      path,
      perf: Math.round(lhr.categories.performance.score * 100),
      a11y: Math.round(lhr.categories.accessibility.score * 100),
      best: Math.round(lhr.categories['best-practices'].score * 100),
      seo: Math.round(lhr.categories.seo.score * 100),
      // The two numbers that usually decide the performance score.
      lcp: lhr.audits['largest-contentful-paint']?.displayValue,
      cls: lhr.audits['cumulative-layout-shift']?.displayValue,
      tbt: lhr.audits['total-blocking-time']?.displayValue,
    };
    rows.push(row);

    console.log(
      `${path.padEnd(38)} perf ${String(row.perf).padStart(3)}  a11y ${String(row.a11y).padStart(3)}` +
        `  best ${String(row.best).padStart(3)}  seo ${String(row.seo).padStart(3)}` +
        `   LCP ${row.lcp}  CLS ${row.cls}  TBT ${row.tbt}`
    );
  }

  await chrome.kill();

  const mean = (k) => Math.round(rows.reduce((s, r) => s + r[k], 0) / rows.length);
  console.log(`\n${label} MEAN   perf ${mean('perf')}  a11y ${mean('a11y')}  best ${mean('best')}  seo ${mean('seo')}`);
  console.log(`reports in ${OUT}`);

  writeFileSync(join(OUT, `${label}-summary.json`), JSON.stringify(rows, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});