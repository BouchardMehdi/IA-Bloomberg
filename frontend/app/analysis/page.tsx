"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { UsdQuoteDetails, type UsdQuote } from "../usd-quote";
import { ResearchRanking } from "./research-ranking";
import { CompanyPublications } from "./company-publications";
import { FinancialResults } from "./financial-results";
import { Opportunity } from "./opportunity";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Instrument = { id: string; symbol: string; exchange: string; name: string;
  currency: string; quote_multiplier: string; usd_valuation: UsdQuote;
  wls_eligibility: { status: string };
  latest_price: { close: string; date: string; source_url: string; stale: boolean } | null };
type Card = { event_id: string; title: string; kind: string; summary: string | null;
  relationship: { basis: string; role: string; quote: string | null }; evidence: string | null;
  sources: Array<{ url: string; published_at: string }>;
  coverage: { analyzed_count: number; selected_count: number; coverage_ratio: number; document_truncated: boolean } | null;
  impact: string; horizon: string; checks: string[] };
type Research = { instrument: Instrument; items: Card[]; next_offset: number | null; notice: string };
async function read<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${api}/market${path}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error("Impossible de charger les analyses.");
  return response.json();
}
const date = (value: string) => new Date(value).toLocaleString("fr-FR");
const basis: Record<string, string> = { security_mention: "Mention de ce titre et de sa cotation", issuer_mention: "Mention de l’émetteur", issuer_document: "Document de l’émetteur — rôle dans le fait à vérifier" };

export default function AnalysisPage() {
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [selected, setSelected] = useState("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<Research | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    read<{ items: Instrument[] }>("/instruments", controller.signal).then((data) => {
      setInstruments(data.items); setSelected((current) => current || data.items[0]?.id || "");
      if (!data.items.length) setLoading(false);
    }).catch((e: Error) => { if (!controller.signal.aborted) { setError(e.message); setLoading(false); } });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    read<Research>(`/instruments/${selected}/research?offset=${offset}`, controller.signal)
      .then((data) => { setResult(data); setLoading(false); })
      .catch((e: Error) => { if (!controller.signal.aborted) { setError(e.message); setLoading(false); } });
    return () => controller.abort();
  }, [selected, offset, revision]);
  function navigate(id: string, page: number) {
    setLoading(true); setResult(null); setError(""); setSelected(id); setOffset(page);
    setRevision((value) => value + 1);
  }
  async function selectRanked(id: string) {
    if (!instruments.some((instrument) => instrument.id === id)) {
      try { const data = await read<{ items: Instrument[] }>("/instruments"); setInstruments(data.items); }
      catch { setError("Impossible de charger la liste des titres."); return; }
    }
    navigate(id, 0);
    document.getElementById("research-details")?.scrollIntoView({ behavior: "smooth" });
  }
  return <main className="mx-auto max-w-5xl px-5 py-8 text-slate-300">
    <header className="mb-6"><h1 className="font-display text-3xl text-white">Analyses des titres suivis</h1>
      <nav className="mt-3 flex gap-5 text-sm text-signal underline"><Link href="/">Veille</Link><Link href="/portfolio">Titres et portefeuille simulé</Link></nav>
    </header>
    <p className="mb-5 text-sm leading-6">Les fiches rapprochent les documents et faits sourcés des titres suivis. Un lien avec l’émetteur ne prouve pas un effet sur une classe d’action. Les points à examiner sont des questions, pas des prévisions.</p>
    <p className="mb-5 text-sm"><Link href="/calendar" className="text-signal underline">Calendrier, estimations et résultats sourcés →</Link></p>
    <ResearchRanking onSelect={(id) => { void selectRanked(id); }} />
    {error ? <p role="alert" className="text-rose-300">{error}</p> : null}
    {!loading && !instruments.length && !error ? <p>Ajoute un titre dans <Link href="/portfolio" className="text-signal underline">le portefeuille</Link> pour consulter ses documents. La liste WLS reste à fournir.</p> : null}
    {instruments.length ? <label id="research-details" className="block">Titre suivi<select value={selected} onChange={(e) => navigate(e.target.value, 0)} className="mt-2 block w-full rounded border border-white/20 bg-slate-950 p-3">{instruments.map((i) => <option key={i.id} value={i.id}>{i.symbol} · {i.exchange} · {i.name}</option>)}</select></label> : null}
    {loading ? <p role="status" className="mt-5">Chargement…</p> : null}
    {selected ? <Opportunity key={`opportunity-${selected}-${revision}`} instrumentId={selected} /> : null}
    {selected ? <CompanyPublications key={selected} instrumentId={selected} onCollected={() => navigate(selected, 0)} /> : null}
    {selected ? <FinancialResults key={`financial-${selected}`} instrumentId={selected} /> : null}
    {result ? <>
      <section className="my-6 rounded-xl border border-white/10 p-5">
        <p className="text-sm text-amber-300">{result.instrument.wls_eligibility.status === "verified" ? "Titre présent dans l’export WLS importé." : "Éligibilité WLS non vérifiée : nouveaux achats simulés bloqués."}</p>
        {result.instrument.latest_price ? <p className="mt-3">Clôture locale : {result.instrument.latest_price.close} × {result.instrument.quote_multiplier} {result.instrument.currency} · séance du {result.instrument.latest_price.date} · <a className="text-signal underline" href={result.instrument.latest_price.source_url} target="_blank" rel="noreferrer">Source du cours</a></p> : <p className="mt-3">Cours indisponible.</p>}
        <div className="mt-2 text-sm"><UsdQuoteDetails quote={result.instrument.usd_valuation} /></div>
        <p className="mt-3 text-sm">{result.notice}</p>
      </section>
      {!result.items.length ? <p>Aucun document daté ou fait associé sur cette page. Cela ne prouve pas l’absence de nouvelles.</p> : null}
      {result.items.map((card) => <article key={card.event_id} className="mb-5 rounded-xl border border-white/10 p-5">
        <p className="text-xs uppercase text-signal">{card.kind === "extracted_fact" ? "Fait extrait à vérifier" : "Publication documentaire"}</p>
        <h2 className="mt-2 text-xl text-white">{card.title}</h2>
        <p className="mt-2 text-sm text-amber-300">{basis[card.relationship.basis]} · rôle identifié : {card.relationship.role}</p>
        {card.summary ? <p className="mt-3">{card.summary}</p> : null}
        {card.evidence ? <blockquote className="my-3 border-l-2 border-signal/40 pl-3 text-sm">{card.evidence}</blockquote> : null}
        {card.relationship.quote && card.relationship.quote !== card.evidence ? <p className="my-3 text-sm">Mention utilisée pour le rapprochement : « {card.relationship.quote} »</p> : null}
        <ul className="mt-3 text-sm">{card.sources.map((source) => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer" className="text-signal underline">Document source</a> · publié le {date(source.published_at)}</li>)}</ul>
        {card.coverage ? <p className="mt-3 text-xs">Couverture : {card.coverage.analyzed_count}/{card.coverage.selected_count} passages · {Math.round(card.coverage.coverage_ratio * 100)} % du texte. {card.coverage.document_truncated ? "Document tronqué à la récupération." : ""} Consulter le document complet.</p> : null}
        <p className="mt-4 text-sm">Impact : {card.impact}</p><p className="mt-2 text-sm">Horizon : {card.horizon}</p>
        <details className="mt-3 text-sm"><summary className="cursor-pointer text-white">Points et risques à examiner</summary><ul className="mt-2 list-disc space-y-2 pl-5">{card.checks.map((check) => <li key={check}>{check}</li>)}</ul></details>
      </article>)}
      <div className="flex gap-5 text-signal"><button disabled={!offset || loading} onClick={() => navigate(selected, Math.max(0, offset - 20))} className="disabled:opacity-40">Précédent</button><button disabled={result.next_offset === null || loading} onClick={() => navigate(selected, result.next_offset ?? offset)} className="disabled:opacity-40">Suivant</button></div>
    </> : null}
  </main>;
}
