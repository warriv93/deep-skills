#!/usr/bin/env node
// Runs axe-core (WCAG 2.1 A/AA) on each URL in headless Chromium.
// Usage: a11y.mjs [--storage <playwright storage state>] [--out <json>] <url>...
// Prints one line per fact:
//   A11Y <url> violations=<n> critical=<c> serious=<s> moderate=<m> minor=<i>
//   VIOLATION <url> <impact> <rule id> nodes=<n> <first target> | <help>
//   A11Y_FAILED <url> <reason>
// Exit 0 always; the caller grades the lines.
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const cache = join(homedir(), ".cache", "axe-playwright");
if (!existsSync(join(cache, "node_modules", "@axe-core", "playwright"))) {
  mkdirSync(cache, { recursive: true });
  execSync("npm i --silent --no-audit --no-fund --prefix . playwright @axe-core/playwright", { cwd: cache, stdio: "ignore" });
  execSync("npx playwright install chromium", { cwd: cache, stdio: "ignore" });
}
const require = createRequire(join(cache, "package.json"));
const { chromium } = require("playwright");
const AxeBuilder = require("@axe-core/playwright").default;

const args = process.argv.slice(2);
let storage, out;
const urls = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--storage") storage = args[++i];
  else if (args[i] === "--out") out = args[++i];
  else urls.push(args[i]);
}

const browser = await chromium.launch();
const context = await browser.newContext(storage ? { storageState: storage } : {});
const report = {};
for (const url of urls) {
  const page = await context.newPage();
  try {
    await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
    const { violations } = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const count = (impact) => violations.filter((v) => v.impact === impact).length;
    console.log(
      `A11Y ${url} violations=${violations.length} critical=${count("critical")} serious=${count("serious")} moderate=${count("moderate")} minor=${count("minor")}`,
    );
    for (const v of violations) {
      console.log(`VIOLATION ${url} ${v.impact} ${v.id} nodes=${v.nodes.length} ${v.nodes[0]?.target.join(" ")} | ${v.help}`);
    }
    report[url] = violations;
  } catch (e) {
    console.log(`A11Y_FAILED ${url} ${String(e.message).split("\n")[0]}`);
  } finally {
    await page.close();
  }
}
await browser.close();
if (out) writeFileSync(out, JSON.stringify(report, null, 2));
