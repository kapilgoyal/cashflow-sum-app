import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const OUT = process.env.OUT_DIR;
if (!OUT) throw new Error("OUT_DIR required");
fs.mkdirSync(OUT, { recursive: true });

const panes = [
  { id: "scenarios", file: "type-baseline-scenarios.png" },
  { id: "asf", file: "type-baseline-tape.png" },
  { id: "qc", file: "type-baseline-qc.png" },
  { id: "cohort", file: "type-baseline-cohort.png" },
  { id: "collateral", file: "type-baseline-collateral.png" },
];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();

for (const pane of panes) {
  await context.addInitScript((navId) => {
    localStorage.setItem("cashflow.navPane", navId);
    localStorage.setItem("cashflow.navCollapsed", "0");
  }, pane.id);
  await page.goto("http://127.0.0.1:5173/", { waitUntil: "networkidle" });
  await page.waitForTimeout(1800);
  const dest = path.join(OUT, pane.file);
  await page.screenshot({ path: dest, fullPage: false });
  console.log("wrote", dest);
}

await browser.close();
