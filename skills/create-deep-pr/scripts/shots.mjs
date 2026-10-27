#!/usr/bin/env node
// Screenshots each URL in headless Chromium, downsized to at most --max px wide (default 800).
// Usage: shots.mjs [--storage <playwright storage state>] [--out <dir>] [--max 800] <url>@<WxH>[#<name>]...
// Prints one line per fact:
//   SHOT <file> <w>x<h>
//   SHOT_FAILED <url> <reason>
// Exit 0 always; the caller grades the lines. Never read the PNGs yourself: hand the SHOT lines to a cheap subagent.
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join, resolve } from "node:path";

const cache = join(homedir(), ".cache", "axe-playwright");
if (!existsSync(join(cache, "node_modules", "playwright"))) {
  mkdirSync(cache, { recursive: true });
  execSync("npm i --silent --no-audit --no-fund --prefix . playwright @axe-core/playwright", { cwd: cache, stdio: "ignore" });
  execSync("npx playwright install chromium", { cwd: cache, stdio: "ignore" });
}
const require = createRequire(join(cache, "package.json"));
const { chromium } = require("playwright");

const args = process.argv.slice(2);
let storage, out = join(tmpdir(), "shots"), max = 800;
const targets = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--storage") storage = args[++i];
  else if (args[i] === "--out") out = args[++i];
  else if (args[i] === "--max") max = Number(args[++i]);
  else targets.push(args[i]);
}
out = resolve(out);
mkdirSync(out, { recursive: true });

const slug = (s) => s.replace(/^https?:\/\//, "").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80);

const browser = await chromium.launch();
for (const target of targets) {
  const m = target.match(/^(.*)@(\d+)x(\d+)(?:#(.+))?$/);
  if (!m) {
    console.log(`SHOT_FAILED ${target} expected <url>@<WxH>[#<name>]`);
    continue;
  }
  const [, url, w, h, name] = m;
  const file = join(out, `${name ?? slug(url)}.png`);
  const context = await browser.newContext({
    viewport: { width: Number(w), height: Number(h) },
    deviceScaleFactor: Math.min(1, max / Number(w)),
    ...(storage ? { storageState: storage } : {}),
  });
  try {
    const page = await context.newPage();
    await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
    await page.screenshot({ path: file });
    const png = readFileSync(file);
    console.log(`SHOT ${file} ${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`);
  } catch (e) {
    console.log(`SHOT_FAILED ${url} ${String(e.message).split("\n")[0]}`);
  } finally {
    await context.close();
  }
}
await browser.close();
