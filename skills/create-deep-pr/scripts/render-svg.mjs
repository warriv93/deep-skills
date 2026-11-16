#!/usr/bin/env node
// Renders an SVG (an Egon.io .egn.svg domain story, say) to a PNG at 2x on white, for a PR body:
// GitHub doesn't render an embedded SVG reliably.
// Usage: render-svg.mjs <svg> <png>
// Prints RENDERED <png> <w>x<h>, or RENDER_FAILED <svg> <reason> and exits 1.
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";

const [svgPath, pngArg] = process.argv.slice(2);
if (!svgPath || !pngArg) {
  console.error("usage: render-svg.mjs <svg> <png>");
  process.exit(2);
}
const png = resolve(pngArg);

const cache = join(homedir(), ".cache", "axe-playwright");
if (!existsSync(join(cache, "node_modules", "playwright"))) {
  mkdirSync(cache, { recursive: true });
  execSync("npm i --silent --no-audit --no-fund --prefix . playwright @axe-core/playwright", { cwd: cache, stdio: "ignore" });
  execSync("npx playwright install chromium", { cwd: cache, stdio: "ignore" });
}
const require = createRequire(join(cache, "package.json"));
const { chromium } = require("playwright");

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ deviceScaleFactor: 2 });
  await page.setContent(`<html><body style="margin:0;background:#fff">${readFileSync(svgPath, "utf8")}</body></html>`);
  const svg = await page.$("svg");
  if (!svg) throw new Error("no <svg> element");
  mkdirSync(dirname(png), { recursive: true });
  await svg.screenshot({ path: png });
  const out = readFileSync(png);
  console.log(`RENDERED ${png} ${out.readUInt32BE(16)}x${out.readUInt32BE(20)}`);
} catch (e) {
  console.log(`RENDER_FAILED ${svgPath} ${String(e.message).split("\n")[0]}`);
  process.exitCode = 1;
} finally {
  await browser.close();
}
