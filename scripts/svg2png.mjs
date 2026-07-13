// Rasterise the README's SVGs to PNG.
//
// The README is rendered by both GitHub and PyPI, and PyPI is the fussy one:
//
//   * relative paths do not resolve there (it has no repo context), so image URLs must be
//     absolute, and
//   * raw.githubusercontent.com serves .svg as text/plain, so a browser will not draw it.
//
// Between them, the README can only use PNGs at absolute raw URLs. Rich's SVG export also
// relies on textLength and per-span positioning, which rsvg-convert renders badly (it
// collapses the spacing), so rasterise in a real browser engine instead.
//
//   node scripts/svg2png.mjs
//
// Requires playwright: npx playwright install chromium

import { chromium } from 'playwright';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const IMAGES = [
  'assets/logo.svg',
  'assets/screenshots/download-dashboard-interrupted.svg',
  'assets/screenshots/os-finder-help.svg',
  'assets/screenshots/os-download-help.svg',
];

const browser = await chromium.launch();

for (const relative of IMAGES) {
  const source = resolve(root, relative);
  const target = source.replace(/\.svg$/, '.png');

  const page = await browser.newPage({ deviceScaleFactor: 2 });
  await page.goto('file://' + source);

  // Take the SVG's declared size: a laid-out bounding box gets clipped by the viewport.
  const box = await page.evaluate(() => {
    const svg = document.querySelector('svg');
    const viewBox = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    return {
      width: Math.ceil(parseFloat(svg.getAttribute('width')) || viewBox[2]),
      height: Math.ceil(parseFloat(svg.getAttribute('height')) || viewBox[3]),
    };
  });

  await page.setViewportSize(box);
  await page.screenshot({ path: target });
  await page.close();

  console.log(`wrote ${target.replace(root + '/', '')}  ${box.width}x${box.height}`);
}

await browser.close();
