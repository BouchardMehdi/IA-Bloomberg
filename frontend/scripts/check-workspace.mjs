// All API responses, including writes, are simulated. No real account/order/import.
import assert from "node:assert/strict";
import { existsSync, mkdirSync } from "node:fs";
import { chromium } from "playwright";

const base = process.env.UI_BASE_URL ?? "http://localhost:3000";
const executablePath = process.env.UI_BROWSER_PATH ?? ["C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"].find(existsSync);
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const context = await browser.newContext({ viewport: { width: 390, height: 950 } });
const page = await context.newPage();
const errors = [], writes = [];
page.on("pageerror", e => errors.push(e.message));
let user = null, read = false, expired = false;
const fixtureUser = { id: "user-test", username: "equipe", role: "admin", enabled: true };
const instrumentId = "00000000-0000-4000-8000-000000000001";
const proposalId = "00000000-0000-4000-8000-000000000002";
const stamp = "2026-10-01T10:00:00Z";
await page.route("**/api/v1/**", async route => {
  const r = route.request(), path = new URL(r.url()).pathname.replace("/api/v1", "");
  const body = r.method() === "GET" ? null : r.postDataJSON();
  let status = 200, data = {};
  if (body) writes.push({ path, body });
  if (path === "/auth/me") data = { auth_enabled: true, user };
  else if (path === "/auth/login") {
    if (body.password !== "test-password-only") { status = 401; data = { detail: "Identifiants incorrects." }; }
    else { user = { ...fixtureUser }; expired = false; data = user; }
  } else if (expired || !user) { status = 401; data = { detail: "Connexion requise." }; }
  else if (path === "/auth/logout") { user = null; data = { ok: true }; }
  else if (path === "/workspace/alerts/alert-test/read") { read = true; data = { ok: true }; }
  else if (path === "/workspace/alerts") data = { items: [{ id: "alert-test", kind: "publication", title: "Document de test", message: "À vérifier dans la source.", read, created_at: stamp, published_at: stamp, url: "https://example.org/proof", page: "/analysis" }], total: 1, unread_count: read ? 0 : 1, notice: "Fixture" };
  else if (path === "/market/instruments") data = { items: [{ id: instrumentId, symbol: "QA", exchange: "XPAR" }] };
  else if (path === "/market/portfolios") data = { items: [{ id: "portfolio-test", name: "Simulation de test" }] };
  else if (path === "/workspace/import-status") data = { enabled: false, items: [] };
  else if (path === "/workspace/imports") data = { items: [{ index: 0, status: "accepted", result: { inserted: true } }] };
  else if (path === "/workspace/proposals") data = { items: [{ id: proposalId, instrument_id: instrumentId, kind: "dividend", effective_date: "2026-09-01", payment_date: "2026-09-10", net_amount_per_security: "1.5", currency: "EUR", source_url: "https://example.org/proof", published_at: stamp, note: "Déclaration de test, aucune opération réelle." }], next_offset: null };
  else if (path === `/workspace/proposals/${proposalId}/apply`) data = { inserted: true };
  else if (path === "/auth/users") data = r.method() === "GET" ? { items: [fixtureUser] } : { id: "created-test", ...body, password: undefined };
  else { throw new Error(`Unexpected fixture route ${path}`); }
  await route.fulfill({ status, contentType: "application/json", headers: { "Access-Control-Allow-Origin": new URL(base).origin, "Access-Control-Allow-Credentials": "true" }, body: JSON.stringify(data) });
});
mkdirSync(".ui-check", { recursive: true });
try {
  await page.goto(`${base}/alerts`);
  await page.getByRole("button", { name: "Se connecter", exact: true }).waitFor();
  assert.equal(await page.getByRole("navigation", { name: "Navigation principale", exact: true }).count(), 0);
  await page.getByLabel("Identifiant", { exact: true }).fill("equipe");
  await page.getByLabel("Mot de passe", { exact: true }).fill("wrong");
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "Identifiants incorrects" }).waitFor();
  await page.getByLabel("Mot de passe", { exact: true }).fill("test-password-only");
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await page.getByRole("heading", { name: "Mes alertes", exact: true }).waitFor();
  await page.getByRole("button", { name: "Marquer comme lue", exact: true }).click();
  await page.getByText("0 alerte(s) non lue(s)", { exact: true }).waitFor();
  await page.reload();
  await page.getByRole("heading", { name: "Mes alertes", exact: true }).waitFor();
  await page.goto(`${base}/settings`);
  await page.getByRole("heading", { name: "Mon espace", exact: true }).waitFor();
  await page.getByText("Format de l’import et saisie avancée", { exact: true }).click();
  await page.getByLabel("Contenu JSON de l’import").fill("not json");
  await page.getByRole("button", { name: "Vérifier et importer", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "JSON valide" }).waitFor();
  assert(!writes.some(w => w.path === "/workspace/imports"));
  await page.getByLabel("Contenu JSON de l’import").fill(JSON.stringify({ items: [{ kind: "earnings", instrument_id: instrumentId, observation: {} }] }));
  await page.getByRole("button", { name: "Vérifier et importer", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "Traitement terminé" }).waitFor();
  assert.equal(writes.filter(w => w.path === "/workspace/imports").length, 1);
  await page.getByRole("button", { name: "Opérations proposées", exact: true }).click();
  const apply = page.getByRole("button", { name: "Appliquer à la simulation", exact: true });
  await apply.waitFor(); assert(await apply.isDisabled());
  await page.getByLabel("Simulation concernée").selectOption("portfolio-test");
  assert(await apply.isDisabled());
  await page.getByRole("checkbox", { name: /J’ai vérifié/ }).check();
  assert(await apply.isEnabled()); await apply.click();
  await page.getByRole("status").filter({ hasText: "Opération traitée" }).waitFor();
  assert.equal(writes.filter(w => w.path.endsWith("/apply")).length, 1);
  await page.getByRole("button", { name: "Comptes de l’équipe", exact: true }).click();
  await page.getByRole("heading", { name: "Comptes de l’équipe", exact: true }).waitFor();
  await page.screenshot({ path: ".ui-check/workspace-accounts-390.png", fullPage: true });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.getByRole("button", { name: "Déconnexion", exact: true }).click();
  await page.getByRole("button", { name: "Se connecter", exact: true }).waitFor();
  user = { ...fixtureUser, role: "viewer" };
  await page.reload();
  await page.getByText("Accès en lecture seule.", { exact: false }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Comptes de l’équipe", exact: true }).count(), 0);
  assert.equal(await page.getByRole("button", { name: "Vérifier et importer", exact: true }).count(), 0);
  expired = true;
  await page.goto(`${base}/alerts`);
  await page.getByRole("button", { name: "Se connecter", exact: true }).waitFor();
  assert.deepEqual(errors, []);
  console.log("Workspace UI passed: login, errors, reload, read alert, import validation, explicit proposal approval, roles, logout and expired session. All writes simulated.");
} finally { await browser.close(); }
