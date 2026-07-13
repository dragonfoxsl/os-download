// Rasterise the README's SVGs to PNG.
//
// The same README is rendered on PyPI, which has no repo context: a relative image path
// 404s there, which is what broke the logo on the 0.1.0 project page. Image URLs must be
// absolute. PNG is used rather than SVG because it renders everywhere without depending on
// a third party's content-type or a renderer's SVG policy.
//
// Rich's SVG export relies on textLength and per-span positioning, which rsvg-convert
// renders badly (it collapses the spacing), so rasterise in a real browser engine instead.
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
