"use client";

import { apiFetch } from "../lib/api";

import Link from "next/link";
import { PageHeader, Pagination, usePagination } from "../components/ui";
import { useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";
const input = "w-full rounded-lg border border-white/15 bg-slate-950 p-2 text-sm text-white";
type Row = { instrument_id: string; symbol: string; exchange: string; name: string; currency: string;
  missing: string[]; usd_status: string; collection_error: string | null; retry_at: string | null;
  price: { date: string; source_url: string } | null; valuation: { status: string; reasons: string[] } };
type Coverage = { watched_count: number; counts: Record<string, number>; items: Row[]; notice: string; observed_at: string;
  price_collection: { items: Array<{ provider: string; remaining_today: number; blocked_until: string | null }> } };
type Instrument = { id: string; symbol: string; exchange: string; currency: string; quote_multiplier: string };
type Preparation = { issuer_candidates: Array<{ id: string; value: string; unit: string; start: string; end: string; source_url: string; filed: string }>;
  notice: string; required: string[]; candidates_limited: boolean };
const labels: Record<string, string> = { missing_price: "Cours manquant", missing_fx: "Taux manquant", stale: "Cours ou taux ancien",
  invalid_conversion: "Conversion invalide", wls_unverified: "WLS non vérifié", listing_unresolved: "Cotation non résolue",
  price_mapping_missing: "Cours manuel, collecte à raccorder", valuation_blocked: "Valorisation bloquée",
  valuation_reference_missing: "Référence de valorisation manquante", financials_unavailable: "Collecte financière indisponible",
  price_collection_error: "Erreur de collecte de cours" };

async function request<T>(path: string, body?: unknown): Promise<T> {
  const r = await apiFetch(`${api}/market${path}`, body === undefined ? { cache: "no-store" } : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Données incomplètes ou incompatibles. Consulter le format documenté dans l’API.");
  return d;
}

export default function CoveragePage() {
  const [data, setData] = useState<Coverage | null>(null);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [filter, setFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const [preparation, setPreparation] = useState<Preparation | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [mappingInstrument, setMappingInstrument] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([request<Coverage>("/coverage"), request<{ items: Instrument[] }>("/instruments")])
      .then(([d, i]) => { if (active) { setData(d); setInstruments(i.items); } })
      .catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [revision]);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    request<Preparation>(`/instruments/${selected}/valuation-preparation`).then(d => { if (active) setPreparation(d); })
      .catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [selected, revision]);
  const rows = data?.items.filter(r => (!filter || r.missing.includes(filter)) &&
    `${r.symbol} ${r.exchange} ${r.name}`.toLowerCase().includes(search.toLowerCase())) ?? [];
  const paged = usePagination(rows, 10, `${filter}|${search}`);
  return <main className="mx-auto max-w-6xl px-5 py-8 text-slate-300">
    <PageHeader title="Qualité des données" description="Identifiez ce qui manque pour analyser un titre ou valoriser votre simulation. Cliquez sur un compteur pour filtrer les titres." />
    <p className="mt-4 text-sm">{data?.notice ?? "Chargement…"}</p>
    {error && <p role="alert" className="mt-4 rounded-lg border border-amber-300/30 p-3 text-amber-300">{error}</p>}
    {notice && <p role="status" className="mt-4 text-signal">{notice}</p>}
    <section className="mt-6 rounded-2xl border border-white/10 p-5">
      <div className="flex flex-wrap justify-between gap-3"><h2 className="text-xl text-white">{data?.watched_count ?? "—"} titres suivis</h2><button className="text-sm text-signal underline" onClick={() => { setError(""); setRevision(v => v + 1); }}>Actualiser</button></div>
      <p className="mt-2 text-xs text-slate-500">Observation : {data ? new Date(data.observed_at).toLocaleString("fr-FR") : "—"}. Les compteurs peuvent se recouper.</p>
      <div className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-3">{Object.entries(data?.counts ?? {}).map(([k, n]) => <button key={k} className={`rounded-xl border p-3 text-left ${filter === k ? "border-signal" : "border-white/10"}`} onClick={() => setFilter(filter === k ? "" : k)}><span className="block text-xs text-slate-400">{labels[k] ?? k}</span><span className="text-2xl text-white">{n}</span></button>)}</div>
      {data?.price_collection.items.map(p => <p key={p.provider} className="mt-3 text-xs text-amber-300">{p.provider} : {p.remaining_today} requêtes restantes aujourd’hui (UTC){p.blocked_until ? ` · suspendu jusqu’au ${new Date(p.blocked_until).toLocaleString("fr-FR")}` : ""}.</p>)}
      <div className="mt-5 grid gap-3 sm:grid-cols-2"><label className="text-xs">Rechercher<input className={input} value={search} onChange={e => setSearch(e.target.value)} /></label><label className="text-xs">Données à compléter<select aria-label="Données à compléter" className={input} value={filter} onChange={e => setFilter(e.target.value)}><option value="">Tous les titres</option>{Object.entries(labels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label></div>
      <ul id="coverage-results" className="mt-4 space-y-3">{paged.items.map(r => <li key={r.instrument_id} className="rounded-xl border border-white/10 p-4">
        <h3 className="text-lg text-white">{r.symbol} · {r.exchange} <span className="text-sm text-slate-400">{r.name}</span></h3>
        <p className="mt-2 text-xs text-amber-300">{r.missing.map(k => labels[k] ?? k).join(" · ") || "Aucun blocage détecté dans cette couverture"}</p>
        {r.price && <a className="mt-2 block text-xs underline" href={r.price.source_url} target="_blank" rel="noreferrer">Dernier cours : {r.price.date}</a>}
        {r.collection_error && <p className="mt-2 text-xs">Collecte : {r.collection_error}{r.retry_at ? ` · reprise au plus tôt ${new Date(r.retry_at).toLocaleString("fr-FR")}` : ""}</p>}
        <details className="mt-2 text-xs"><summary className="cursor-pointer">Blocages de valorisation</summary><ul className="mt-2 list-inside list-disc">{r.valuation.reasons.map(v => <li key={v}>{v}</li>)}</ul></details>
        <button className="mt-3 text-sm text-signal underline" onClick={() => { if (selected !== r.instrument_id) setPreparation(null); setSelected(r.instrument_id); requestAnimationFrame(() => document.getElementById("valuation-preparation")?.scrollIntoView({ behavior: "smooth" })); }}>Préparer les preuves de valorisation</button>
      </li>)}</ul>{!rows.length && <p className="mt-4 text-sm">Aucun titre pour ce filtre.</p>}
      <Pagination page={paged.page} pageSize={10} total={paged.total} onChange={paged.onChange} label="titres" targetId="coverage-results" />
    </section>
    {selected && <section id="valuation-preparation" className="mt-6 rounded-2xl border border-white/10 p-5"><h2 className="text-xl text-white">Préparation : {instruments.find(i => i.id === selected)?.symbol}</h2>
      <p className="mt-3 text-sm">{preparation?.notice ?? "Chargement…"}</p><ul className="mt-3 list-inside list-disc text-sm">{preparation?.required.map(v => <li key={v}>{v}</li>)}</ul>
      <h3 className="mt-4 text-white">Candidats documentaires SEC de l’émetteur</h3>
      {preparation && !preparation.issuer_candidates.length && <p className="mt-2 text-sm text-slate-400">Aucun candidat annuel dans la couverture disponible. Aucun BPA inventé.</p>}
      <ul className="mt-3 space-y-3 text-sm">{preparation?.issuer_candidates.map(c => <li key={c.id}><a href={c.source_url} target="_blank" rel="noreferrer" className="underline">{c.start} → {c.end} · {c.value} {c.unit} · dépôt du {c.filed}</a><p className="text-xs text-amber-300">BPA de l’émetteur, correspondance par titre à documenter avant calcul.</p></li>)}</ul>
      <Link href="/analysis" className="mt-4 inline-block text-sm text-signal underline">Saisir les preuves complètes dans la fiche Analyse →</Link>
    </section>}
    <details className="mt-6 rounded-2xl border border-white/10 p-5"><summary className="cursor-pointer text-xl text-white">Raccorder une cotation internationale à Alpha Vantage</summary>
      <p className="mt-3 text-sm">Fournir le symbole exact documenté par le fournisseur, sa place, sa devise et son unité. Aucun suffixe n’est déduit. La correspondance reste déclarée ; le fournisseur contrôle ensuite son symbole de réponse. Le quota est partagé avec les cours US et le calendrier.</p>
      <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={async e => {
        e.preventDefault(); setBusy(true); setError(""); setNotice(""); const f = new FormData(e.currentTarget);
        const i = instruments.find(i => i.id === mappingInstrument);
        try { if (!i) throw new Error("Choisis une cotation.");
          await request("/price-mappings", { instrument_id: i.id, symbol: i.symbol, exchange: i.exchange,
            currency: i.currency, quote_multiplier: i.quote_multiplier, provider: "alpha_vantage", provider_symbol: f.get("provider_symbol"),
            source_url: f.get("source_url"), published_at: new Date(String(f.get("published_at"))).toISOString(),
            as_of: f.get("as_of"), note: f.get("note"), confirmed: true });
          setNotice("Correspondance enregistrée. La collecte automatique la prendra en compte au prochain cycle, selon le quota disponible."); setRevision(v => v + 1);
        } catch (e) { setError(e instanceof Error ? e.message : "Erreur."); } finally { setBusy(false); }
      }}>
        <label className="text-xs">Cotation<select aria-label="Cotation" className={input} value={mappingInstrument} onChange={e => setMappingInstrument(e.target.value)} required><option value="">Choisir</option>{instruments.filter(i => !["NYSE", "Nasdaq"].includes(i.exchange)).map(i => <option key={i.id} value={i.id}>{i.symbol} · {i.exchange} · {i.currency} · unité {i.quote_multiplier}</option>)}</select></label>
        <label className="text-xs">Symbole Alpha Vantage exact<input name="provider_symbol" className={input} required maxLength={50} /></label>
        <label className="text-xs">URL de la preuve<input name="source_url" type="url" className={input} required /></label>
        <label className="text-xs">Publication (heure locale)<input name="published_at" type="datetime-local" className={input} required /></label>
        <label className="text-xs">Correspondance valable au<input name="as_of" type="date" className={input} required /></label>
        <label className="text-xs sm:col-span-2">Preuve de la cotation, devise et unité<textarea name="note" className={input} minLength={20} maxLength={1500} required /></label>
        <label className="text-xs sm:col-span-2"><input type="checkbox" required /> Je confirme la correspondance exacte et l’unité. La saisie ne certifie pas le fournisseur ou le WLS.</label>
        <button disabled={busy} className="rounded-lg bg-signal p-2 text-sm font-semibold text-slate-950 disabled:opacity-40">Activer la collecte pour cette cotation</button>
      </form><Link href="/international" className="mt-4 inline-block text-sm text-signal underline">Ajouter d’abord une identité internationale sourcée →</Link>
    </details>
    <details className="mt-6 rounded-2xl border border-white/10 p-5"><summary className="cursor-pointer text-xl text-white">Importer des preuves de valorisation en lot</summary>
      <p className="mt-3 text-sm">Fichier JSON de 100 observations maximum, format <code>{'{"items":[{"instrument_id":"…","observation":{…}}]}'}</code>. Chaque observation reprend tous les champs du formulaire de valorisation. Les incohérences de format bloquent le fichier ; les refus métier sont détaillés par ligne. Les observations acceptées restent enregistrées.</p>
      <a className="mt-2 block text-xs text-signal underline" href={`${api.replace(/\/api\/v1$/, "")}/docs`} target="_blank" rel="noreferrer">Consulter le schéma ValuationBatch dans l’API</a>
      <input type="file" accept="application/json,.json" disabled={busy} className="mt-4 block text-sm" onChange={async e => {
        const file = e.target.files?.[0]; if (!file) return;
        setBusy(true); setError(""); setNotice("");
        try { if (file.size > 1000000) throw new Error("Fichier limité à 1 Mo.");
          const d = await request<{ saved_count: number; items: Array<{ status: string; reason?: string; instrument_id: string }> }>("/valuations/batch", JSON.parse(await file.text()));
          setNotice(`${d.saved_count} observation(s) acceptée(s). ${d.items.filter(i => i.status === "rejected").map(i => `${i.instrument_id} : ${i.reason}`).join(" · ")}`); setRevision(v => v + 1);
        } catch (e) { setError(e instanceof Error ? e.message : "Import impossible."); } finally { setBusy(false); }
      }} />
    </details>
  </main>;
}
