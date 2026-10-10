"use client";

import { Pagination } from "../components/ui";
import { useEffect, useState } from "react";
import { UsdQuoteDetails, type UsdQuote } from "../usd-quote";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type RankedFact = { event_id: string; title: string; summary: string | null; evidence: string;
  published_at: string; relationship: { basis: string; role: string };
  date_reference: { url: string; published_at: string };
  sources: Array<{ url: string; published_at: string }> };
type RankedItem = { rank: number; score: number; research_status: string;
  instrument: { id: string; symbol: string; exchange: string; name: string };
  recent_fact_count: number; recent_publication_count: number; scored_publication_count: number;
  components: Array<{ code: string; label: string; points: number; maximum: number; event_ids: string[] }>;
  facts: RankedFact[]; checks: string[]; usd_valuation: UsdQuote;
  data_checks: Array<{ code: string; status: string; message: string; source_url: string | null; as_of: string | null }> };
type Ranking = { items: RankedItem[]; total_tracked: number; next_offset: number | null;
  as_of: string; window_days: number; notice: string;
  coverage: { limited: boolean; events_examined: number; event_limit: number } };
const published = (value: string) => new Date(value).toLocaleString("fr-FR");
const statusClass = (status: string) => ["available", "verified", "not_required"].includes(status) ? "text-slate-300" : "text-amber-300";

export function ResearchRanking({ onSelect }: { onSelect: (id: string) => void }) {
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<Ranking | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  function reload(page: number) {
    setLoading(true); setError(""); setResult(null); setOffset(page);
    setRevision((value) => value + 1);
  }
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${api}/market/research-ranking?limit=5&offset=${offset}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Impossible de charger le classement.");
        return response.json() as Promise<Ranking>;
      }).then((data) => { if (!controller.signal.aborted) { setResult(data); setLoading(false); } })
      .catch((e: Error) => { if (!controller.signal.aborted) { setError(e.message); setLoading(false); } });
    return () => controller.abort();
  }, [offset, revision]);
  return <section className="mb-8 rounded-2xl border border-white/10 p-5" aria-labelledby="ranking-title">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="ranking-title" className="font-display text-2xl text-white">Titres à examiner en priorité</h2>
      <button onClick={() => reload(0)} disabled={loading} className="text-sm text-signal underline disabled:opacity-40">Actualiser le classement</button>
    </div>
    <p className="mt-3 text-sm leading-6">Score de priorité de recherche sur les 30 derniers jours : récence, précision du lien avec le titre, type du fait et publications distinctes. Les données de marché et le WLS sont contrôlés séparément. Ce score ne prédit ni hausse ni rentabilité.</p>
    <details className="mt-3 text-sm"><summary className="cursor-pointer text-white">Comment le score est calculé</summary>
      <p className="mt-2 leading-6">Nous retenons un fait par publication, puis au maximum trois publications. Récence : 30 points jusqu’à 48 h, 20 jusqu’à 7 jours, 10 jusqu’à 30 jours. Lien : 30 pour une mention du titre et de sa cotation, 15 pour son émetteur. Type déclaré : 25 pour résultats, opérations d’entreprise ou procédures, 15 pour réglementation, 5 pour les autres types. Publications : 5 points chacune. Pour les trois premiers critères, seule la meilleure valeur retenue compte. Les publications seules ne rapportent aucun point.</p>
    </details>
    {loading ? <p role="status" className="mt-4">Chargement du classement…</p> : null}
    {error ? <p role="alert" className="mt-4 text-rose-300">{error}</p> : null}
    {result ? <>
      <p className="mt-3 text-xs text-slate-400">{result.total_tracked} titre(s) suivi(s) · période de {result.window_days} jours · calcul du {published(result.as_of)}</p>
      {result.coverage.limited ? <p className="mt-3 text-sm text-amber-300">Classement partiel : seuls les {result.coverage.event_limit} événements candidats les plus récents ont été examinés. Certains faits peuvent manquer ; les scores ne couvrent pas toute la période.</p> : null}
      {!result.total_tracked ? <p className="mt-4 text-sm">Ajoute les titres que tu souhaites suivre dans le portefeuille ou la page internationale. Aucun titre de démonstration n’est chargé.</p> : !result.items.length ? <p className="mt-4 text-sm">Aucun titre sur cette page. Reviens à la première page ou actualise le classement.</p> : null}
      <div className="mt-5 space-y-4">{result.items.map((item) => <article key={item.instrument.id} className="rounded-xl border border-white/10 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h3 className="text-lg text-white">{item.rank}. {item.instrument.symbol} · {item.instrument.exchange}</h3><p className="text-sm text-slate-400">{item.instrument.name}</p></div>
          <div className="text-right"><p className="text-xl text-signal">{item.score}/100</p><p className="text-xs text-slate-400">Priorité de recherche</p></div>
        </div>
        <p className="mt-3 text-sm">{item.research_status === "facts_to_review" ? `${item.recent_fact_count} fait(s) rapproché(s) ; score fondé sur ${item.scored_publication_count} publication(s) distincte(s).` : item.research_status === "documents_only" ? "Documents disponibles, sans fait extrait et rapproché permettant de calculer une priorité." : "Aucun fait ou document récent rapproché dans cette couverture. Cela ne signifie pas absence de nouvelles."}</p>
        <ul className="mt-3 space-y-1 text-sm">{item.data_checks.map((check) => <li key={check.code} className={statusClass(check.status)}>{check.message}{check.source_url ? <> · <a href={check.source_url} className="underline" target="_blank" rel="noreferrer">Source{check.as_of ? ` du ${check.as_of}` : ""}</a></> : null}</li>)}</ul>
        <div className="mt-2 text-sm"><UsdQuoteDetails quote={item.usd_valuation} /></div>
        <details className="mt-4 text-sm"><summary className="cursor-pointer text-white">Pourquoi ce score ?</summary>
          <ul className="mt-3 space-y-2">{item.components.map((component) => <li key={component.code}>{component.label} : <span className="text-white">{component.points}/{component.maximum}</span>{component.event_ids.length ? <span className="ml-2">{component.event_ids.map((id) => <a key={id} href={`#rank-fact-${item.instrument.id}-${id}`} className="mr-2 text-signal underline">Fait {item.facts.findIndex((fact) => fact.event_id === id) + 1}</a>)}</span> : null}</li>)}</ul>
        </details>
        {item.facts.map((fact, index) => <div id={`rank-fact-${item.instrument.id}-${fact.event_id}`} key={fact.event_id} className="mt-4 border-t border-white/10 pt-3 text-sm">
          <p className="text-xs text-amber-300">{fact.relationship.basis === "security_mention" ? "Mention du titre et de sa cotation" : "Mention de l’émetteur ; effet sur ce titre à vérifier"} · rôle extrait : {fact.relationship.role}</p>
          <h4 className="mt-2 text-white">Fait {index + 1} · {fact.title}</h4>{fact.summary ? <p className="mt-2">{fact.summary}</p> : null}
          <p className="mt-2 text-xs text-slate-400">Date retenue pour le classement : {published(fact.published_at)} · <a href={fact.date_reference.url} className="text-signal underline" target="_blank" rel="noreferrer">Source de cette date</a></p>
          <blockquote className="mt-2 border-l-2 border-signal/30 pl-3 text-slate-400">{fact.evidence}</blockquote>
          <ul className="mt-2">{fact.sources.map((source) => <li key={source.url}><a href={source.url} className="text-signal underline" target="_blank" rel="noreferrer">Document source</a> · publié le {published(source.published_at)}</li>)}</ul>
        </div>)}
        <details className="mt-4 text-sm"><summary className="cursor-pointer text-white">Points et risques à vérifier</summary><ul className="mt-2 list-disc space-y-2 pl-5">{item.checks.map((check) => <li key={check}>{check}</li>)}</ul></details>
        <button onClick={() => onSelect(item.instrument.id)} className="mt-4 text-sm text-signal underline">Ouvrir la fiche documentaire</button>
      </article>)}</div>
      <Pagination page={offset / 5} pageSize={5} total={result.total_tracked} busy={loading} onChange={p => reload(p * 5)} label="titres à examiner" targetId="ranking-title" />
    </> : null}
  </section>;
}
