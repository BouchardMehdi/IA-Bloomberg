"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { UsdQuoteDetails, type UsdQuote } from "../usd-quote";
import { WlsCandidates } from "./wls-candidates";
import { PortfolioHistory } from "./history";
import { PortfolioActions } from "./actions";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Money = string | number;
type Instrument = { id: string; symbol: string; name: string; exchange: string; currency: string;
  quote_multiplier: string; price_provider: string; usd_valuation: UsdQuote;
  wls_eligibility: { status: string; security_id: string | null; source_url: string | null; as_of: string | null };
  wls_preparation: { status: string; evidence: { bloomberg_identifier: string } | null };
  latest_price: { close: Money; date: string; source_url: string; stale: boolean } | null;
  collection_status: string; error_code: string | null; retry_at: string | null };
type Market = { items: Instrument[]; provider_configured: boolean; daily_request_budget: number; wls_imported: boolean; wls_security_count: number };
type PriceCollection = { quota_day: string; items: Array<{ provider: string; configured: boolean;
  attempts_today: number; daily_request_budget: number; remaining_today: number; blocked_until: string | null }> };
type Portfolio = { id: string; name: string; wls_policy: string; initial_capital: Money; cash: Money; total_value: Money | null;
  total_pnl: Money | null; realized_pnl: Money; return_pct: Money | null; valuation_stale: boolean;
  fee_bps: Money; max_position_pct: Money; allowed_symbols: string[]; starts_on: string | null; ends_on: string | null;
  positions: Array<{ instrument_id: string; symbol: string; exchange: string; quantity: number; cost_basis: Money;
    value: Money | null; unrealized_pnl: Money | null; quote_date: string | null; stale: boolean }>;
  trades: Array<{ id: string; instrument_id: string; symbol: string; exchange: string; side: string; quantity: number; price: Money; fee: Money;
    quote_date: string; quote_source_url: string; executed_at: string; realized_pnl: Money;
    universe_evidence: { policy: string; bloomberg_identifier?: string; source_hash: string } | null;
    conversion: { local_close: string; currency: string; quote_multiplier: string; usd_per_unit: string; fx_date: string | null; fx_source_url: string | null } | null }> };
const input = "w-full rounded-lg border border-white/15 bg-slate-950 p-2 text-sm text-white";
const button = "rounded-lg bg-signal px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40";
const usd = (v: Money | null) => v === null ? "Indisponible" : new Intl.NumberFormat("fr-FR", { style: "currency", currency: "USD" }).format(Number(v));

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${api}/market${path}`, body === undefined ? { cache: "no-store" } : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Vérifie les valeurs du formulaire.");
  return payload as T;
}

export default function PortfolioPage() {
  const [market, setMarket] = useState<Market | null>(null);
  const [priceCollection, setPriceCollection] = useState<PriceCollection | null>(null);
  const [portfolios, setPortfolios] = useState<Array<{ id: string; name: string }>>([]);
  const [selected, setSelected] = useState("");
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState("");
  const [name, setName] = useState("Challenge — paramètres provisoires");
  const [capital, setCapital] = useState("1000000");
  const [wlsPolicy, setWlsPolicy] = useState("declared_partial");
  const [fees, setFees] = useState("10");
  const [cap, setCap] = useState("25");
  const [allowed, setAllowed] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [instrument, setInstrument] = useState("");
  const [side, setSide] = useState("buy");
  const [quantity, setQuantity] = useState("1");
  const submission = useRef<{ fingerprint: string; key: string } | null>(null);

  const load = useCallback(async () => {
    const [m, p, c] = await Promise.all([request<Market>("/instruments"), request<{ items: Array<{ id: string; name: string }> }>("/portfolios"), request<PriceCollection>("/price-collection")]);
    setMarket(m); setPortfolios(p.items); setPriceCollection(c);
  }, []);
  useEffect(() => {
    let active = true;
    Promise.all([request<Market>("/instruments"), request<{ items: Array<{ id: string; name: string }> }>("/portfolios"), request<PriceCollection>("/price-collection")])
      .then(([m, p, c]) => { if (active) { setMarket(m); setPortfolios(p.items); setPriceCollection(c); } })
      .catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    request<Portfolio>(`/portfolios/${selected}`).then((p) => { if (active) setPortfolio(p); }).catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [selected]);

  async function act(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "Erreur de connexion."); }
    finally { setBusy(false); }
  }

  return <main className="mx-auto max-w-6xl px-5 py-8 text-slate-300">
    <header className="mb-8 flex items-center justify-between">
      <div><p className="text-xs uppercase tracking-widest text-signal">Market AI</p><h1 className="mt-2 font-display text-3xl text-white">Portefeuille simulé</h1></div>
      <nav className="flex gap-4"><Link href="/coverage" className="text-sm text-signal underline">Couverture des données</Link><Link href="/" className="text-sm text-signal underline">Retour à la veille</Link></nav>
    </header>
    <p className="mb-6 rounded-xl border border-signal/20 bg-signal/5 p-4 text-sm leading-6">
      Règles communiquées : 1 000 000 USD, actions uniquement, positions longues, sans levier ni trading de devises ou de matières premières. L’univers WLS porte sur des titres distincts, pas sur des entreprises.
      Les actions internationales et leurs devises locales sont autorisées. La collecte automatique couvre actuellement NYSE/Nasdaq en USD ; les autres cotations et taux peuvent être fournis depuis des sources autorisées. Les frais, la durée et la limite par position restent à confirmer.
      Les opérations utilisent le dernier cours de clôture disponible ; ce prix ne garantit pas une exécution réelle. Les dividendes et fractionnements ne sont pas comptabilisés automatiquement.
    </p>
    {error ? <p role="alert" className="mb-4 rounded bg-rose-950/50 p-3 text-rose-300">{error}</p> : null}
    {notice ? <p role="status" className="mb-4 text-signal">{notice}</p> : null}
    <section className="rounded-2xl border border-white/10 p-5">
      <h2 className="font-display text-xl text-white">Titres suivis et cours quotidiens</h2>
      {priceCollection?.items.filter((p) => p.configured).map((p) => <p key={p.provider} className="mt-3 text-sm text-slate-400">
        Alpha Vantage : {p.attempts_today}/{p.daily_request_budget} tentatives le {priceCollection.quota_day} (UTC), {p.remaining_today} restantes.
        {p.blocked_until ? ` Quota fournisseur signalé ; reprise au plus tôt le ${new Date(p.blocked_until).toLocaleString("fr-FR")}.` : p.remaining_today === 0 ? " Budget local épuisé ; reprise au prochain jour UTC." : ""}
      </p>)}
      <Link href="/international" className="mt-2 inline-block text-sm text-signal underline">Titres internationaux et taux de conversion →</Link>
      {market ? <p className="mt-3 text-sm text-amber-300">{market.wls_imported ? `Export WLS daté chargé : ${market.wls_security_count} titres. L’éligibilité stricte est vérifiée par ticker et marché.` : "Aucun export WLS daté : le mode strict bloque les achats. Une simulation provisoire peut utiliser la liste déclarée pour les cotations résolues. Le référentiel SEC seul ne prouve pas l’appartenance au WLS."}</p> : null}
      {market?.items.length ? <ul className="mt-2 text-xs text-slate-400">{market.items.map((i) => <li key={i.id}>{i.symbol} · {i.exchange} : {i.wls_eligibility.status === "verified" ? `Action présente dans l’export WLS (${i.wls_eligibility.security_id})` : i.wls_preparation.status === "matched" ? "Cotation résolue ; simulation provisoire disponible, composition WLS non datée" : "Éligibilité WLS non vérifiée"}</li>)}</ul> : null}
      {market && !market.provider_configured ? <p className="mt-3 text-sm text-amber-300">Les cours ne sont pas activés. Ajoute ta clé personnelle ALPHA_VANTAGE_API_KEY dans .env, puis recrée backend et scheduler avec Docker. Aucun cours de démonstration n’est utilisé pour le portefeuille.</p> : null}
      <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); act(async () => {
        await request("/instruments", { symbol: symbol.trim().toUpperCase(), exchange: exchange || null });
        setSymbol(""); await load(); setNotice("Titre ajouté. La collecte automatique vérifiera les cours lors du prochain cycle horaire.");
      }); }}>
        <label className="text-xs">Ticker<input className={input} placeholder="Ticker à suivre" value={symbol} onChange={(e) => setSymbol(e.target.value)} required maxLength={20} /></label>
        <label className="text-xs">Marché<select className={input} value={exchange} onChange={(e) => setExchange(e.target.value)}><option value="">Détection par la SEC</option><option>NYSE</option><option>Nasdaq</option></select></label>
        <button className={button} disabled={busy}>Ajouter à la liste</button>
        <button type="button" className="px-3 py-2 text-sm text-signal underline" disabled={busy} onClick={() => act(async () => { await load(); if (selected) setPortfolio(await request<Portfolio>(`/portfolios/${selected}`)); })}>Actualiser l’affichage</button>
      </form>
      <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-slate-500"><tr><th className="p-2">Titre</th><th>Clôture locale</th><th>Équivalent USD par titre</th><th>Date du cours</th><th>Collecte</th></tr></thead><tbody>
        {market?.items.map((i) => <tr key={i.id} className="border-t border-white/10"><td className="p-2">{i.symbol} · {i.exchange}<span className="block text-xs text-slate-500">{i.name}</span></td><td>{i.latest_price ? `${i.latest_price.close} × ${i.quote_multiplier} ${i.currency}` : "En attente"}</td><td><UsdQuoteDetails quote={i.usd_valuation} /></td><td>{i.latest_price ? <a href={i.latest_price.source_url} target="_blank" rel="noreferrer" className="underline">{i.latest_price.date}{i.latest_price.stale ? " · ancien" : ""}</a> : "—"}</td><td>{i.price_provider === "manual" ? "Données fournies" : i.error_code ? "Erreur fournisseur" : i.collection_status === "success" ? "Synchronisé" : "En attente"}</td></tr>)}
      </tbody></table></div>
      {!market?.items.length ? <p className="mt-3 text-sm text-slate-500">Ajoute les tickers que tu souhaites observer. Cette liste n’est pas une recommandation d’investissement.</p> : null}
    </section>
    <WlsCandidates instruments={market?.items ?? []} onRefresh={load} />
    <section className="mt-6 rounded-2xl border border-white/10 p-5">
      <h2 className="font-display text-xl text-white">Configurer une simulation</h2>
      <form className="mt-4 grid gap-3 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); act(async () => {
        const p = await request<{ id: string }>("/portfolios", { name, initial_capital: capital, fee_bps: fees, max_position_pct: cap,
          wls_policy: wlsPolicy, allowed_symbols: allowed.split(",").map((s) => s.trim()).filter(Boolean), starts_on: start || null, ends_on: end || null });
        await load(); setPortfolio(null); setSelected(p.id); setNotice("Simulation créée avec les paramètres choisis.");
      }); }}>
        <label className="text-xs">Nom<input className={input} value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} /></label>
        <label className="text-xs">Univers de simulation<select className={input} value={wlsPolicy} onChange={(e) => setWlsPolicy(e.target.value)}><option value="declared_partial">Provisoire : liste WLS fournie, non datée</option><option value="verified">Strict : export WLS daté et rapproché</option></select></label>
        <p className="text-xs text-amber-300 sm:col-span-3">Le mode provisoire utilise la liste déclarée après résolution de la cotation et du type d’action. Il ne certifie pas les règles ou la composition actuelle du challenge. Les frais restent des paramètres de simulation.</p>
        <label className="text-xs">Capital initial USD<input type="number" min="1" max="1000000000" step="0.01" className={input} value={capital} onChange={(e) => setCapital(e.target.value)} required /></label>
        <label className="text-xs">Frais par opération en points de base (10 = 0,10 %)<input type="number" min="0" max="1000" step="0.01" className={input} value={fees} onChange={(e) => setFees(e.target.value)} required /></label>
        <label className="text-xs">Poids maximal par titre (%)<input type="number" min="0.01" max="100" step="0.01" className={input} value={cap} onChange={(e) => setCap(e.target.value)} required /></label>
        <label className="text-xs sm:col-span-2">Tickers autorisés, séparés par des virgules (vide : tous les titres suivis)<input className={input} value={allowed} onChange={(e) => setAllowed(e.target.value)} /></label>
        <label className="text-xs">Début facultatif<input type="date" className={input} value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label className="text-xs">Fin facultative<input type="date" className={input} value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        <button className={`${button} self-end`} disabled={busy}>Créer le portefeuille simulé</button>
      </form>
    </section>
    <section className="mt-6 rounded-2xl border border-white/10 p-5">
      <h2 className="font-display text-xl text-white">Suivre le portefeuille</h2>
      <label className="mt-3 block text-xs">Simulation<select className={`${input} mt-1`} value={selected} disabled={busy} onChange={(e) => { setPortfolio(null); setSelected(e.target.value); submission.current = null; }}><option value="">Choisir un portefeuille</option>{portfolios.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      {portfolio ? <>
        <p className="mt-3 text-sm text-amber-300">{portfolio.wls_policy === "declared_partial" ? "Simulation provisoire sur liste WLS partielle déclarée, date inconnue. Performance distincte du challenge officiel." : "Simulation stricte : achat soumis à l’export WLS daté."}</p>
        <div className="my-5 grid gap-3 sm:grid-cols-4">{[["Capital disponible", usd(portfolio.cash)], ["Valeur totale", usd(portfolio.total_value)], ["Gain / perte total", usd(portfolio.total_pnl)], ["Performance", portfolio.return_pct === null ? "Indisponible" : `${portfolio.return_pct} %`]].map(([label, value]) => <div key={label} className="rounded bg-white/5 p-3"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-lg text-white">{value}</p></div>)}</div>
        <p className="text-xs text-slate-400">Capital initial : {usd(portfolio.initial_capital)} · Frais : {portfolio.fee_bps} pb · Limite par titre : {portfolio.max_position_pct} % · Gain/perte réalisé : {usd(portfolio.realized_pnl)}<br />Titres autorisés : {portfolio.allowed_symbols.join(", ") || "Tous les titres suivis"} · Période : {portfolio.starts_on ?? "sans début imposé"} → {portfolio.ends_on ?? "sans fin imposée"}</p>
        {portfolio.valuation_stale ? <p className="mt-2 text-sm text-amber-300">Valorisation partielle ou fondée sur des cours anciens. Actualise les données avant de simuler un achat.</p> : null}
        <form className="my-5 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); act(async () => {
          const fingerprint = JSON.stringify({ selected, instrument, side, quantity });
          if (submission.current?.fingerprint !== fingerprint) submission.current = { fingerprint, key: crypto.randomUUID() };
          await request(`/portfolios/${selected}/orders`, { instrument_id: instrument, client_order_id: submission.current.key, side, quantity: Number(quantity) });
          setPortfolio(await request<Portfolio>(`/portfolios/${selected}`)); submission.current = null; setNotice("Opération simulée enregistrée au dernier cours de clôture disponible.");
        }); }}>
          <label className="text-xs">Titre<select className={input} value={instrument} onChange={(e) => setInstrument(e.target.value)} required><option value="">Choisir</option>{market?.items.map((i) => <option key={i.id} value={i.id}>{i.symbol} · {i.exchange}</option>)}</select></label>
          <label className="text-xs">Opération<select className={input} value={side} onChange={(e) => setSide(e.target.value)}><option value="buy">Achat simulé</option><option value="sell">Vente simulée</option></select></label>
          <label className="text-xs">Nombre de titres<input type="number" min="1" max="1000000" step="1" className={input} value={quantity} onChange={(e) => setQuantity(e.target.value)} required /></label>
          <button className={button} disabled={busy || !instrument || market?.items.find((i) => i.id === instrument)?.usd_valuation.status !== "available" || (side === "buy" && market?.items.find((i) => i.id === instrument)?.wls_eligibility.status !== "verified" && !(portfolio.wls_policy === "declared_partial" && market?.items.find((i) => i.id === instrument)?.wls_preparation.status === "matched"))}>Enregistrer la simulation</button>
        </form>
        <h3 className="mb-2 text-white">Positions</h3><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-slate-500"><tr><th>Titre</th><th>Quantité</th><th>Coût frais inclus</th><th>Valeur</th><th>Gain/perte latent</th></tr></thead><tbody>{portfolio.positions.map((p) => <tr key={p.instrument_id} className="border-t border-white/10"><td className="py-2">{p.symbol} · {p.exchange}</td><td>{p.quantity}</td><td>{usd(p.cost_basis)}</td><td>{usd(p.value)}</td><td>{usd(p.unrealized_pnl)}</td></tr>)}</tbody></table></div>
        {!portfolio.positions.length ? <p className="text-sm text-slate-500">Aucune position ouverte.</p> : null}
        <PortfolioHistory key={selected} portfolioId={selected} revision={JSON.stringify([portfolio.cash, portfolio.total_value, portfolio.trades[0]?.id])} />
        <PortfolioActions key={`${selected}-actions`} portfolioId={selected} instruments={market?.items ?? []} onChange={async () => { setPortfolio(await request<Portfolio>(`/portfolios/${selected}`)); }} />
        <h3 className="mb-2 mt-5 text-white">Dernières opérations</h3><ul className="space-y-2 text-sm">{portfolio.trades.map((t) => <li key={t.id} className="border-t border-white/10 pt-2">{t.side === "buy" ? "Achat" : "Vente"} simulé · {t.quantity} {t.symbol} × {usd(t.price)} · Frais {usd(t.fee)}<span className="block text-xs text-slate-500">Enregistré le {new Date(t.executed_at).toLocaleString("fr-FR")} · <a className="underline" href={t.quote_source_url} target="_blank" rel="noreferrer">Clôture du {t.quote_date}</a></span>{t.conversion ? <span className="block text-xs text-slate-400">Cours local {t.conversion.local_close} × {t.conversion.quote_multiplier} {t.conversion.currency} · 1 {t.conversion.currency} = {t.conversion.usd_per_unit} USD · {t.conversion.fx_source_url ? <a href={t.conversion.fx_source_url} target="_blank" rel="noreferrer" className="underline">taux du {t.conversion.fx_date}</a> : "devise USD"}</span> : null}</li>)}</ul>
      </> : <p className="mt-4 text-sm text-slate-500">Crée ou sélectionne une simulation pour suivre sa performance.</p>}
    </section>
  </main>;
}
