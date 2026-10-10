// Browser checks use fixtures only: no provider quota, saved observation or order.
import assert from "node:assert/strict";
import { existsSync, mkdirSync } from "node:fs";
import { chromium } from "playwright";

const base = process.env.UI_BASE_URL ?? "http://localhost:3000";
const screenshotDir = process.env.UI_SCREENSHOTS_DIR ?? ".ui-check";
const executablePath = process.env.UI_BROWSER_PATH ?? [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
].find(existsSync);
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
mkdirSync(screenshotDir, { recursive: true });
const stamp = "2026-10-09T10:00:00Z";
const source = "https://example.org/published-document";
const many = (n, fn) => Array.from({ length: n }, (_, i) => fn(i));
const quote = { status: "missing_price", price_usd: null, stale: false, conversion: null };
const instruments = many(35, i => ({ id: `instrument-${i}`, symbol: `TEST${String(i).padStart(2, "0")}`,
  name: `Société de test ${i}`, exchange: i < 23 ? "Nasdaq" : "XPAR", currency: i < 23 ? "USD" : "EUR",
  quote_multiplier: "1", price_provider: i < 23 ? "alpha_vantage" : "manual", usd_valuation: quote,
  wls_eligibility: { status: "unverified", security_id: null }, wls_preparation: { status: "matched", evidence: null },
  latest_price: null, collection_status: "pending", error_code: null, registry_url: source, identity_as_of: "2026-10-09", isin: null,
}));
const articles = many(19, i => ({ id: `article-${i}`, title: `Publication de test ${i}`, source_name: "Source de test",
  url: source, content: "Document utilisé uniquement pour vérifier la présentation.", content_status: "success",
  published_at: i === 0 ? null : stamp, fetched_at: stamp, content_truncated: false }));
const events = many(13, i => ({ id: `event-${i}`, event_type: "official_publication", title: `Événement de test ${i}`,
  source_name: "Source de test", article_url: source, event_datetime: stamp, parent_event_id: null,
  semantic_analysis: null, entity_resolution: null, companies: [], sources: [{ article_id: `article-${i}`, source_name: "Source de test", url: source, published_at: stamp }],
}));
const rates = many(19, i => ({ currency: `FX${i}`, date: "2026-10-09", usd_per_unit: "1.10", provider: "ecb", source_url: source }));
const observations = many(21, i => ({ id: `observation-${i}`, kind: "schedule", provider: "manual", report_date: "2026-11-01",
  fiscal_period_end: "2026-09-30", period_type: "quarterly", basis: "unknown", eps: null, currency: null, source_url: source,
  published_at: stamp, observed_at: stamp }));
const financials = many(21, i => ({ id: `fact-${i}`, metric: "revenue", concept: "RevenueFromContractWithCustomerExcludingAssessedTax",
  taxonomy: "us-gaap", value: "1000000", unit: "USD", start: "2025-10-01", end: "2026-09-30", filed: "2026-10-09",
  accession: `0000000000-26-${String(i).padStart(6, "0")}`, form: "10-K", source_url: source, observed_at: stamp, comparison: null }));
const trades = many(13, i => ({ id: `trade-${i}`, instrument_id: `instrument-${i}`, symbol: `TEST${i}`, exchange: "Nasdaq",
  side: "buy", quantity: 1, price: "100", fee: "1", quote_date: "2026-10-09", quote_source_url: source, executed_at: stamp, conversion: null }));
const positions = instruments.slice(0, 12).map(i => ({ instrument_id: i.id, symbol: i.symbol, exchange: i.exchange,
  quantity: 1, cost_basis: "100", value: null, unrealized_pnl: null }));
const portfolio = { id: "portfolio-test", name: "Simulation de test", wls_policy: "declared_partial", initial_capital: "1000000",
  cash: "998788", total_value: null, total_pnl: null, realized_pnl: "0", return_pct: null, valuation_stale: true,
  fee_bps: "10", max_position_pct: "25", allowed_symbols: [], starts_on: null, ends_on: null, positions, trades };
const history = many(12, i => ({ id: `point-${i}`, date: `2026-09-${String(i + 1).padStart(2, "0")}`,
  observed_at: stamp, status: "available", total_value: "1000000", return_pct: "0", cash: "1000000", positions: [] }));
const collection = { configured: true, supported: true, status: "failed", error_code: "provider_invalid_response",
  retry_at: "2026-10-10T11:00:00Z", started_at: stamp, coverage_current: true, scheduler_enabled: true, fetched_count: 0, cik: "0000000001" };
const requests = [], unexpected = [], browserErrors = [];
let mode = "normal";

function payload(url) {
  const path = url.pathname.replace("/api/v1", "");
  const limit = Number(url.searchParams.get("limit") ?? 10), offset = Number(url.searchParams.get("offset") ?? 0);
  const paged = items => ({ items: items.slice(offset, offset + limit), total: items.length, limit, offset,
    next_offset: offset + limit < items.length ? offset + limit : null });
  if (path === "/health/live") return { status: "ok" };
  if (path === "/collection-runs") return { items: [], total: 0 };
  if (path === "/articles") return paged(mode === "empty" ? [] : articles);
  if (path === "/events") return paged(mode === "empty" ? [] : events);
  if (path === "/market/instruments") return { items: mode === "empty" ? [] : instruments, provider_configured: true,
    daily_request_budget: 25, wls_imported: false, wls_security_count: 0 };
  if (path === "/market/price-collection") return { quota_day: "2026-10-10", items: [{ provider: "alpha_vantage", configured: true,
    attempts_today: 25, daily_request_budget: 25, remaining_today: 0, blocked_until: stamp }] };
  if (path === "/market/portfolios") return { items: mode === "empty" ? [] : [{ id: portfolio.id, name: portfolio.name }] };
  if (path === "/market/portfolios/portfolio-test") return portfolio;
  if (path.endsWith("/history")) return { items: history, notice: "Historique observé, données de test.", limited: false };
  if (path.endsWith("/actions")) return { items: [] };
  if (path === "/market/fx-rates") return { items: rates };
  if (path === "/market/fx-collection") return { enabled: true, interval_minutes: 60, latest_run: null, last_success: null, source_url: source };
  if (path === "/market/coverage") return { watched_count: instruments.length, observed_at: stamp,
    notice: "Les données manquantes restent indisponibles.", counts: { missing_price: 35, wls_unverified: 35 }, price_collection: { items: [] },
    items: instruments.map(i => ({ instrument_id: i.id, symbol: i.symbol, name: i.name, exchange: i.exchange, missing: ["missing_price", "wls_unverified"],
      price: null, collection_error: null, valuation: { status: "blocked", reasons: ["BPA annuel par titre manquant."] } })) };
  if (path === "/market/research-ranking") return { ...paged(mode === "empty" ? [] : instruments.map((i, index) => ({ rank: index + 1, score: 0,
    instrument: i, research_status: "documents_only", facts: [], checks: ["Vérifier les sources."], data_checks: [], usd_valuation: quote, components: [] }))),
    total_tracked: mode === "empty" ? 0 : instruments.length, window_days: 30, as_of: stamp, coverage: { limited: false } };
  if (path === "/market/wls-candidates") {
    const items = instruments.map(i => ({ bloomberg_identifier: `${i.symbol} US Equity`, source_cell: "A1", automatic_mappings: [], identity_observation: null,
      listing_mapping: null, suggested_instrument: null, mapping_status: "unresolved" })).filter(i => i.bloomberg_identifier.includes(url.searchParams.get("search") ?? ""));
    return { ...paged(items), loaded: true, security_count: 3000, mapped_count: 0, automatic_mapped_count: 0, identity_statuses: {},
      notice: "Liste partielle déclarée, composition non datée.", source_filename: "fixture.xlsx", source_sheet: "Test", observed_at: stamp,
      composition_as_of: null, origin: "Fixture de test", archive_history: [], archive_history_limited: false };
  }
  if (path.endsWith("/research")) return { instrument: instruments[0], ...paged(events.map(e => ({ event_id: e.id, title: e.title, kind: "publication",
    relationship: { basis: "issuer_document", role: "source_subject", quote: null }, sources: [{ url: source, published_at: stamp }],
    coverage: null, impact: "Non établi", horizon: "À vérifier", checks: [] }))), notice: "Le lien documentaire ne prouve pas un impact." };
  if (path.endsWith("/earnings")) return { ...paged(observations), notice: "Prévisions à confirmer.", collection };
  if (path.endsWith("/opportunity")) return { generated_at: stamp, notice: "Dossier de recherche, sans score d’achat.", favorable: [], risks: [],
    liquidity: [], checks: [], upcoming: [], missing_data: ["BPA annuel par titre manquant."], coverage: { limited: false } };
  if (path.endsWith("/financials")) return { ...paged(financials), collection, notice: "Périodes et définitions séparées.", available_metrics: ["revenue"],
    supported_metrics: ["revenue"], metric_labels: { revenue: "Chiffre d’affaires" } };
  if (path.endsWith("/financial-trends")) return { items: [], notice: "Même concept, unité et durée dans un même dépôt.", reason: null, coverage: { limited: false, examined: 0, limit: 2000 } };
  if (path.endsWith("/valuation")) return { instrument: instruments[0], price: null, observation: null, history: [], notice: "Le rendement bénéficiaire n’est pas un rendement futur.",
    calculation: { status: "blocked", reasons: ["BPA annuel GAAP dilué par titre manquant."], pe: null, reference_comparison: null } };
  if (path.endsWith("/valuation-preparation")) return { issuer_candidates: [], required: ["BPA annuel par titre documenté."], notice: "Preuves déclaratives.", candidates_limited: false };
  if (path.endsWith("/publications/collection")) return { ...collection, source_url: source, notice: "Documents de l’émetteur.", inserted_count: 0 };
  unexpected.push(path); return {};
}

const page = await browser.newPage();
page.setDefaultTimeout(15000);
page.on("pageerror", error => browserErrors.push(error.message));
await page.route("**/api/v1/**", async route => {
  const request = route.request(), url = new URL(request.url());
  requests.push(url);
  assert.equal(request.method(), "GET", "UI verification must never write to the API");
  await route.fulfill({ status: mode === "error" ? 503 : 200, contentType: "application/json",
    headers: { "Access-Control-Allow-Origin": "*" }, body: JSON.stringify(mode === "error" ? { detail: "Service indisponible." } : payload(url)) });
});
const paths = ["/", "/analysis", "/calendar", "/portfolio", "/coverage", "/international"];
const names = ["Veille", "Analyser", "Calendrier", "Portefeuille", "Qualité des données", "International"];
const widths = process.env.UI_CHECK_WIDTHS?.split(",").map(Number) ?? [1440, 768, 390, 320];
let checked = 0;
async function settled() { await page.waitForLoadState("networkidle"); }
async function screen(name) {
  await settled();
  const width = await page.evaluate(() => ({ available: innerWidth, content: document.documentElement.scrollWidth }));
  assert(width.content <= width.available + 1, `${name}: horizontal overflow ${JSON.stringify(width)}`);
  assert.equal(await page.locator("main h1").count(), 1, `${name}: one main heading`);
  assert.deepEqual(browserErrors, [], `${name}: browser errors`);
  await page.screenshot({ path: `${screenshotDir}/${name}.png` }); checked++;
}
const pager = label => page.getByRole("navigation", { name: `Pagination : ${label}`, exact: true });
const next = label => pager(label).getByRole("button", { name: `Page suivante : ${label}`, exact: true });
const switchSection = name => page.getByRole("group").getByRole("button", { name, exact: true }).click();
try {
  for (const width of widths) {
    await page.setViewportSize({ width, height: 950 });
    for (let i = 0; i < paths.length; i++) {
      await page.goto(`${base}${paths[i]}`); await settled();
      if (width >= 1024) {
        const nav = page.getByRole("navigation", { name: "Navigation principale", exact: true });
        assert.equal(await nav.getByRole("link").count(), 6);
        assert.equal(await nav.locator('[aria-current="page"]').count(), 1);
      } else {
        await page.getByRole("button", { name: "Ouvrir la navigation" }).click();
        const nav = page.getByRole("navigation", { name: "Navigation mobile", exact: true });
        assert.equal(await nav.getByRole("link").count(), 6);
        assert.equal(await nav.locator('[aria-current="page"]').textContent().then(t => t.trim()), names[i]);
        await nav.getByRole("link").first().focus(); await page.keyboard.press("Escape");
        assert.equal(await nav.isVisible(), false);
        assert.equal(await page.getByRole("button", { name: "Ouvrir la navigation" }).evaluate(e => e === document.activeElement), true);
      }
      await screen(`${width}-${paths[i].slice(1) || "veille"}`);
    }
  }
  await page.setViewportSize({ width: 390, height: 950 });
  await page.goto(base); await settled();
  assert.match(await page.locator("#articles-list").innerText(), /Consulté le/);
  await next("publications").click(); await settled();
  assert.match(await pager("publications").innerText(), /7–12 sur 19/);
  await next("événements").click(); await settled();
  assert.match(await pager("événements").innerText(), /7–12 sur 13/);

  await page.getByRole("button", { name: "Ouvrir la navigation" }).click();
  await page.getByRole("navigation", { name: "Navigation mobile", exact: true }).getByRole("link", { name: "Portefeuille", exact: true }).click();
  await page.waitForURL(`${base}/portfolio`); await settled();
  assert.equal(await page.getByRole("navigation", { name: "Navigation mobile", exact: true }).isVisible(), false);
  await page.getByText("Simulation provisoire sur liste WLS partielle déclarée, date inconnue. Performance distincte du challenge officiel.", { exact: true }).waitFor();
  assert.equal(await page.getByRole("combobox", { name: /^Simulation/ }).inputValue(), "portfolio-test");
  await next("positions").click(); await settled(); assert.match(await pager("positions").innerText(), /11–12 sur 12/);
  await next("opérations récentes").click(); await settled(); assert.match(await pager("opérations récentes").innerText(), /11–13 sur 13/);
  await page.getByText("Valeurs et preuves quotidiennes (12)", { exact: true }).click();
  await next("jours observés").click(); assert.match(await pager("jours observés").innerText(), /11–12 sur 12/);
  await screen("mobile-simulation");
  await switchSection("Titres suivis"); await next("titres suivis").click();
  await page.getByLabel("Rechercher un titre", { exact: true }).fill("TEST34");
  assert.match(await pager("titres suivis").innerText(), /1–1 sur 1/);
  await page.getByLabel("Rechercher un titre", { exact: true }).fill("inexistant");
  assert.match(await pager("titres suivis").innerText(), /Aucun résultat/);
  await page.getByLabel("Rechercher un titre", { exact: true }).fill("");
  assert.match(await pager("titres suivis").innerText(), /1–10 sur 35/); await screen("mobile-titres");
  await switchSection("Univers WLS"); await settled(); await next("titres WLS").click(); await settled();
  assert.match(await pager("titres WLS").innerText(), /11–20 sur 35/);
  await page.getByLabel("Rechercher un identifiant Bloomberg").fill("TEST34");
  await page.getByRole("button", { name: "Rechercher", exact: true }).click(); await settled();
  assert.match(await pager("titres WLS").innerText(), /1–1 sur 1/); await screen("mobile-wls");
  await switchSection("Nouvelle simulation"); await screen("mobile-creation-simulation");

  await page.goto(`${base}/analysis`); await settled(); await next("titres à examiner").click(); await settled();
  assert.match(await pager("titres à examiner").innerText(), /6–10 sur 35/);
  await page.getByRole("button", { name: "Ouvrir la fiche documentaire" }).first().click(); await screen("mobile-synthese");
  assert.equal(await page.getByRole("button", { name: "Synthèse", exact: true }).getAttribute("aria-pressed"), "true");
  await switchSection("Résultats"); await settled(); await page.getByText("Observations détaillées (10 sur cette page)", { exact: true }).click();
  await next("observations financières").click(); await screen("mobile-resultats");
  await switchSection("Valorisation"); await settled(); await page.getByText("Fournir les données nécessaires à la valorisation", { exact: true }).click();
  await screen("mobile-valorisation");
  await switchSection("Documents et faits"); await settled(); await next("documents et faits").click(); await screen("mobile-documents");
  await page.goto(`${base}/calendar`); await settled(); await next("observations").click(); await settled();
  assert.match(await pager("observations").innerText(), /Page 2/); await screen("mobile-calendrier-page2");
  await page.goto(`${base}/coverage`); await settled(); await next("titres").click();
  await page.getByLabel("Rechercher", { exact: true }).fill("TEST34"); assert.match(await pager("titres").innerText(), /1–1 sur 1/);
  await page.getByRole("button", { name: "Préparer les preuves de valorisation" }).click(); await screen("mobile-preuves");
  await page.goto(`${base}/international`); await settled(); await next("cotations").click(); assert.match(await pager("cotations").innerText(), /11–12 sur 12/);
  await switchSection("Ajouter une cotation"); await screen("mobile-identite");
  await switchSection("Cours et taux"); await next("taux").click(); assert.match(await pager("taux").innerText(), /9–16 sur 19/); await screen("mobile-taux");

  mode = "empty";
  for (const path of ["/", "/analysis", "/portfolio", "/calendar"]) { await page.goto(`${base}${path}`); await screen(`empty-${path.slice(1) || "veille"}`); }
  mode = "error";
  for (const path of paths) { await page.goto(`${base}${path}`); await screen(`error-${path.slice(1) || "veille"}`); }
  assert.deepEqual(unexpected, [], "All API requests have fixtures");
  assert.deepEqual(browserErrors, [], "No uncaught browser errors");
  for (const endpoint of ["articles", "events", "research-ranking", "wls-candidates", "financials", "earnings", "research"])
    assert(requests.some(u => u.pathname.endsWith(`/${endpoint}`) && Number(u.searchParams.get("offset")) > 0), `${endpoint}: server pagination exercised`);
  console.log(`UI checks passed: ${checked} screens, six routes, ${widths.length} widths, navigation, pagination, filters and empty/error states. Screenshots: ${screenshotDir}`);
} catch (error) {
  await page.screenshot({ path: `${screenshotDir}/failure.png` });
  console.error("Failed screen:", page.url(), await page.locator("main").innerText());
  throw error;
} finally { await browser.close(); }
