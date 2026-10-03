"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { UsdQuoteDetails, type UsdQuote } from "../usd-quote";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const currencies = ["EUR", "GBP", "HKD", "JPY", "CHF", "CAD", "AUD", "CNY", "SGD", "NZD", "SEK", "NOK", "DKK", "INR", "KRW", "TWD", "BRL", "ZAR", "MXN"];
const input = "mt-1 w-full rounded border border-white/15 bg-slate-950 p-2 text-sm";
const button = "rounded bg-signal px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40";
type Instrument = { id: string; symbol: string; exchange: string; name: string; currency: string;
  isin: string | null; bloomberg_symbol: string | null; quote_multiplier: string; price_provider: string;
  registry_url: string; identity_as_of: string | null; usd_valuation: UsdQuote;
  latest_price: { close: string; date: string; source_url: string } | null };
type Rate = { currency: string; date: string; usd_per_unit: string; source_url: string; provider: string };
type FxRun = { status: string; finished_at: string | null; latest_reference_date: string | null; available_currencies: string[] | null };
type FxStatus = { enabled: boolean; interval_minutes: number; latest_run: FxRun | null; last_success: FxRun | null; source_url: string };
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${api}/market${path}`, body === undefined ? { cache: "no-store" } : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Vérifie les identifiants, les dates et la précision des valeurs.");
  return data;
}
function Provenance({ label }: { label: string }) {
  return <><label className="text-xs">{label}<input name="as_of" type="date" max={new Date().toISOString().slice(0, 10)} className={input} required /></label>
    <label className="text-xs">URL de la source<input name="source_url" type="url" className={input} required /><span className="text-slate-500">Référence accessible avec ton autorisation, sans identifiants ni paramètres secrets.</span></label></>;
}
export default function InternationalPage() {
  const [items, setItems] = useState<Instrument[]>([]);
  const [rates, setRates] = useState<Rate[]>([]);
  const [fxStatus, setFxStatus] = useState<FxStatus | null>(null);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    Promise.all([request<{ items: Instrument[] }>("/instruments"), request<{ items: Rate[] }>("/fx-rates"), request<FxStatus>("/fx-collection")])
      .then(([market, fx, status]) => { if (active) { setItems(market.items); setRates(fx.items); setFxStatus(status); setLoading(false); } })
      .catch((e: Error) => { if (active) { setError(e.message); setLoading(false); } });
    return () => { active = false; };
  }, []);
  async function act(action: () => Promise<void>, message = "Données enregistrées. L’éligibilité WLS reste une vérification séparée.") {
    setBusy(true); setError(""); setNotice("");
    try {
      await action();
      const [market, fx, status] = await Promise.all([request<{ items: Instrument[] }>("/instruments"), request<{ items: Rate[] }>("/fx-rates"), request<FxStatus>("/fx-collection")]);
      setItems(market.items); setRates(fx.items); setFxStatus(status); setNotice(message);
    } catch (e) { setError(e instanceof Error ? e.message : "Erreur de connexion."); }
    finally { setBusy(false); }
  }
  const manual = items.filter((i) => i.price_provider === "manual");
  const instrument = manual.find((i) => i.id === selected);
  return <main className="mx-auto max-w-6xl px-5 py-8 text-slate-300">
    <header><h1 className="font-display text-3xl text-white">Titres internationaux et conversion USD</h1>
      <nav className="mt-3 flex gap-5 text-sm text-signal underline"><Link href="/portfolio">Portefeuille simulé</Link><Link href="/analysis">Analyses</Link></nav></header>
    <p className="my-6 text-sm leading-6">Les actions internationales sont autorisées dans le challenge. Les taux de référence BCE sont récupérés automatiquement et convertis vers USD. Les identités et clôtures internationales restent à fournir depuis tes sources autorisées. Aucun titre WLS n’est déduit de ces données. La conversion sert à valoriser une action en USD, sans position Forex. Ses conventions peuvent différer de celles de Bloomberg.</p>
    {error ? <p role="alert" className="mb-4 text-rose-300">{error}</p> : null}
    {notice ? <p role="status" className="mb-4 text-signal">{notice}</p> : null}
    {loading ? <p role="status">Chargement…</p> : null}
    {fxStatus ? <section className="mb-6 rounded-xl border border-signal/20 p-5">
      <h2 className="text-xl text-white">Collecte automatique des taux</h2>
      <p className="mt-2 text-sm">{fxStatus.enabled ? `Activée · vérification toutes les ${fxStatus.interval_minutes} minutes.` : "Collecte automatique désactivée."} <a href={fxStatus.source_url} target="_blank" rel="noreferrer" className="text-signal underline">Source BCE</a></p>
      {fxStatus.last_success ? <p className="mt-2 text-sm">Dernière date de référence récupérée : {fxStatus.last_success.latest_reference_date} · devises disponibles dans cette publication : {fxStatus.last_success.available_currencies?.join(", ")}.<br />Collecte terminée le {fxStatus.last_success.finished_at ? new Date(fxStatus.last_success.finished_at).toLocaleString("fr-FR") : "—"}.</p> : <p className="mt-2 text-sm">Aucune collecte réussie pour le moment.</p>}
      {fxStatus.latest_run?.status === "failed" ? <p role="status" className="mt-2 text-sm text-amber-300">La dernière collecte a échoué. Les taux précédents sont conservés ; leur ancienneté reste contrôlée avant une simulation.</p> : null}
      <p className="mt-2 text-xs text-slate-400">Taux de référence indicatifs, pas des taux d’exécution. Les devises absentes de la source ne sont pas complétées automatiquement. Une saisie manuelle pour une date donnée garde priorité sur la collecte BCE.</p>
      <button type="button" disabled={busy} className="mt-3 text-sm text-signal underline disabled:opacity-40" onClick={() => act(async () => {}, "Affichage actualisé.")}>Actualiser l’affichage</button>
    </section> : null}
    <section className="rounded-xl border border-white/10 p-5"><h2 className="text-xl text-white">Identifier une cotation</h2>
      <p className="mt-2 text-sm">Un ISIN identifie le titre ; le marché et le ticker distinguent sa cotation. Utilise les identifiants exacts de ta source. Pour NYSE/Nasdaq, utilise l’ajout SEC du portefeuille.</p>
      <form className="mt-4 grid gap-4 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); const data = Object.fromEntries(new FormData(e.currentTarget)); act(async () => {
        const created = await request<{ id: string }>("/international-instruments", { ...data, asset_class: "equity", bloomberg_symbol: data.bloomberg_symbol || null, cik: data.cik || null });
        setSelected(created.id);
      }); }}>
        <label className="text-xs">Ticker local<input name="symbol" className={input} maxLength={20} pattern="[A-Z0-9][A-Z0-9.\-]*" required /></label>
        <label className="text-xs">Code du marché MIC (4 caractères)<input name="exchange" className={input} minLength={4} maxLength={4} pattern="[A-Z0-9]{4}" required /></label>
        <label className="text-xs">ISIN<input name="isin" className={input} minLength={12} maxLength={12} required /></label>
        <label className="text-xs">Nom du titre<input name="name" className={input} maxLength={512} required /></label>
        <label className="text-xs">CIK SEC, seulement s’il est connu (facultatif)<input name="cik" className={input} pattern="[0-9]{10}" maxLength={10} /></label>
        <label className="text-xs">Symbole Bloomberg exact, si disponible<input name="bloomberg_symbol" className={input} maxLength={100} /></label>
        <label className="text-xs">Devise<select name="currency" className={input}>{["USD", ...currencies].map((c) => <option key={c}>{c}</option>)}</select></label>
        <label className="text-xs">Facteur de l’unité du cours<input name="quote_multiplier" type="number" min="0.000001" max="1" step="0.000001" className={input} required /><span className="text-slate-500">1 pour la devise principale ; 0,01 pour des pence cotés en GBP. Vérifier dans la source.</span></label>
        <Provenance label="Date de validité de l’identité" />
        <button className={button} disabled={busy}>Ajouter cette cotation</button>
      </form>
    </section>
    <div className="mt-6 grid gap-6 md:grid-cols-2">
      <section className="rounded-xl border border-white/10 p-5"><h2 className="text-xl text-white">Fournir une clôture locale</h2>
        <form className="mt-4 grid gap-4" onSubmit={(e) => { e.preventDefault(); if (!instrument) return; const data = Object.fromEntries(new FormData(e.currentTarget)); act(async () => {
          await request(`/instruments/${instrument.id}/prices`, { ...data, volume: Number(data.volume), currency: instrument.currency, quote_multiplier: instrument.quote_multiplier });
        }); }}>
          <label className="text-xs">Cotation<select className={input} value={selected} onChange={(e) => setSelected(e.target.value)} required><option value="">Choisir un titre</option>{manual.map((i) => <option key={i.id} value={i.id}>{i.symbol} · {i.exchange} · {i.currency}</option>)}</select></label>
          {instrument ? <p className="text-xs">Devise : {instrument.currency} · facteur du cours : {instrument.quote_multiplier}</p> : null}
          <label className="text-xs">Clôture brute dans l’unité de cotation<input name="close" type="number" min="0.000001" step="0.000001" className={input} required /></label>
          <label className="text-xs">Volume publié<input name="volume" type="number" min="0" max="9007199254740991" step="1" className={input} required /></label>
          <Provenance label="Date de séance" /><button className={button} disabled={busy || !instrument}>Enregistrer le cours</button>
        </form>
      </section>
      <section className="rounded-xl border border-white/10 p-5"><h2 className="text-xl text-white">Fournir un taux complémentaire vers USD</h2>
        <p className="mt-2 text-sm">Sens du taux : 1 unité de la devise = le nombre d’USD indiqué. Si ta source donne le sens inverse, convertir explicitement avant la saisie.</p>
        <form className="mt-4 grid gap-4" onSubmit={(e) => { e.preventDefault(); const data = Object.fromEntries(new FormData(e.currentTarget)); act(async () => { await request("/fx-rates", data); }); }}>
          <label className="text-xs">Devise<select name="currency" className={input}>{currencies.map((c) => <option key={c}>{c}</option>)}</select></label>
          <label className="text-xs">USD pour 1 unité<input name="usd_per_unit" type="number" min="0.0000000001" step="0.0000000001" className={input} required /></label>
          <Provenance label="Date du taux" /><button className={button} disabled={busy}>Enregistrer le taux</button>
        </form>
        <ul className="mt-4 space-y-2 text-xs">{rates.map((r) => <li key={r.currency}>1 {r.currency} = {r.usd_per_unit} USD · <a href={r.source_url} target="_blank" rel="noreferrer" className="text-signal underline">{r.date}</a> · {r.provider === "ecb" ? "Référence BCE convertie" : "Donnée fournie"}</li>)}</ul>
      </section>
    </div>
    <section className="mt-6 rounded-xl border border-white/10 p-5"><h2 className="text-xl text-white">Cours et valorisations des cotations fournies</h2>
      {!manual.length && !loading ? <p className="mt-3">Aucune cotation internationale fournie.</p> : null}
      <ul className="mt-3 space-y-5">{manual.map((i) => <li key={i.id} className="border-t border-white/10 pt-3">
        <p className="text-white">{i.symbol} · {i.exchange} · {i.name}</p><p className="text-xs">ISIN {i.isin} · {i.bloomberg_symbol ?? "Symbole Bloomberg non fourni"} · <a href={i.registry_url} target="_blank" rel="noreferrer" className="text-signal underline">identité au {i.identity_as_of}</a></p>
        <p className="mt-2 text-sm">{i.latest_price ? <>{i.latest_price.close} × {i.quote_multiplier} {i.currency} · <a href={i.latest_price.source_url} target="_blank" rel="noreferrer" className="underline">séance du {i.latest_price.date}</a> · </> : null}<UsdQuoteDetails quote={i.usd_valuation} /></p>
      </li>)}</ul>
      <p className="mt-4 text-xs text-slate-400">La conversion utilise le dernier taux fourni au plus tard à la date du cours. Un cours ou taux trop ancien bloque une nouvelle opération simulée. Les titres restent soumis à la vérification WLS.</p>
    </section>
  </main>;
}
