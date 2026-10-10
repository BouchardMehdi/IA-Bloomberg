// All API requests intercepted; no real account, collection or inference is used.
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true, executablePath: process.env.UI_BROWSER_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe" });
const directory = ".ui-check/ai-status";
mkdirSync(directory, { recursive: true });
const scenarios = [
  ["offline", { enabled:true, mode:"remote", worker_status:"unconfirmed", last_seen_at:null, counts:{pending:3,leased:1,success:12,failed:2} }, "Connexion du PC d’analyse non confirmée"],
  ["online", { enabled:true, mode:"remote", worker_status:"recent", last_seen_at:"2026-10-10T19:00:00Z", counts:{pending:0} }, "PC d’analyse connecté récemment"],
  ["disabled", { enabled:false, mode:"remote", counts:{} }, "Analyse automatique désactivée"],
  ["inline", { enabled:true, mode:"inline", counts:{} }, "Analyse sur l’installation locale"],
  ["error", null, "État de l’IA indisponible"],
];
const errors = [];
try {
  for (const width of [320, 1440]) for (const [name, state, expected] of scenarios) {
    const page = await browser.newPage({ viewport:{width,height:1000} });
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname;
      let payload = {};
      if (path.endsWith("/auth/me")) payload = {auth_enabled:false,user:null};
      if (path.endsWith("/workspace/alerts")) payload = {items:[],total:0,unread_count:0};
      if (path.endsWith("/workspace/collection-health")) payload = {scheduler:{status:"recent",last_seen_at:null},items:[],total:0};
      if (path.endsWith("/workspace/ai-status")) {
        if (!state) return route.fulfill({status:503,contentType:"application/json",body:'{"detail":"Unavailable"}'});
        payload = state;
      }
      await route.fulfill({contentType:"application/json",body:JSON.stringify(payload)});
    });
    await page.goto(`${process.env.UI_BASE_URL ?? "http://127.0.0.1:3100"}/collections`);
    const panel = page.getByRole("region", {name:"État de l’IA"});
    await panel.getByText(expected, {exact:false}).waitFor();
    assert(await panel.isVisible());
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name} overflows at ${width}px`);
    if (name === "offline") await panel.getByText("En attente : 3", {exact:false}).waitFor();
    await page.screenshot({path:`${directory}/${name}-${width}.png`,fullPage:true});
    await page.close();
  }
  assert.deepEqual(errors, []);
  console.log("AI status: 10 screens passed, 320/1440px, offline/online/disabled/inline/API failure.");
} finally { await browser.close(); }
