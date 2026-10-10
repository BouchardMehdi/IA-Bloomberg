"use client";

import { apiFetch } from "../lib/api";

import { useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";
type Source = { url: string; published_at: string };
type Argument = { id: string; label: string; value: string; unit: string; start: string; end: string;
  concept: string; accession: string; sources: Source[]; stale_period: boolean; notice: string };
type Dossier = { generated_at: string; notice: string; favorable: Argument[]; risks: Argument[];
  liquidity: { id: string; label: string; concept: string; value: string; unit: string;
    start: string | null; end: string; filed: string; source_url: string; stale_period: boolean }[];
  checks: { event_id: string; title: string; summary: string | null; evidence: string;
    label: string; sources: Source[]; relationship: { basis: string; role: string };
    coverage: { coverage_ratio: number; document_truncated: boolean } | null }[];
  upcoming: { report_date: string; fiscal_period_end: string; source_url: string;
    published_at: string | null; observed_at: string; provider: string; conflicting_dates: boolean }[];
  missing_data: string[]; coverage: { limited: boolean } };
function Sources({ sources }: { sources: Source[] }) {
  return <ul className="mt-2 text-xs">{sources.map((source) => <li key={`${source.url}-${source.published_at}`}><a href={source.url} target="_blank" rel="noreferrer" className="text-signal underline">Source</a> · publication : {source.published_at}</li>)}</ul>;
}
function Arguments({ items }: { items: Argument[] }) {
  return <>{items.length ? items.map((item) => <article key={item.id} className="my-3 rounded border border-white/10 p-3">
    <p className="text-white">{item.label} : {item.value} {item.unit}</p>
    <p className="mt-1 text-sm">Du {item.start} au {item.end} · {item.concept}</p>
    {item.stale_period ? <p className="mt-1 text-xs text-amber-300">Période terminée depuis plus de 180 jours.</p> : null}
    <p className="mt-2 text-xs">{item.notice}</p><Sources sources={item.sources} />
  </article>) : <p className="my-3 text-sm">Aucun élément qualifié dans les données examinées. La couverture peut être incomplète.</p>}</>;
}

export function Opportunity({ instrumentId }: { instrumentId: string }) {
  const [data, setData] = useState<Dossier | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    apiFetch(`${api}/market/instruments/${instrumentId}/opportunity`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error("Fiche d’opportunité indisponible."); return response.json() as Promise<Dossier>; })
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [instrumentId, revision]);
  return <section className="my-6 rounded-xl border border-signal/25 p-5">
    <div className="flex flex-wrap justify-between gap-3"><h2 className="text-2xl text-white">Fiche d’opportunité</h2><button className="text-sm text-signal underline" onClick={() => { setData(null); setError(""); setRevision((n) => n + 1); }}>Actualiser la fiche</button></div>
    {error ? <p role="alert" className="mt-3 text-rose-300">{error}</p> : null}
    {!data && !error ? <p role="status" className="mt-3">Préparation de la fiche…</p> : null}
    {data ? <>
      <p className="my-3 text-sm">{data.notice}</p>
      <p className="mb-4 text-xs">Calculée le {new Date(data.generated_at).toLocaleString("fr-FR")} · {data.coverage.limited ? "Couverture bornée et partielle" : "Couverture disponible, sans garantie d’exhaustivité"}.</p>
      <div className="grid gap-5 md:grid-cols-2"><div><h3 className="text-lg text-white">Éléments favorables à examiner</h3><Arguments items={data.favorable} /></div><div><h3 className="text-lg text-white">Risques documentés</h3><Arguments items={data.risks} /></div></div>
      <h3 className="mt-5 text-lg text-white">Trésorerie, dette et flux publiés</h3>
      <p className="my-2 text-xs">Soldes à une date et flux sur une période restent séparés. Les fonds restreints, dettes avec crédit-bail et parts courantes ne sont pas additionnés. Aucun ratio de solvabilité, dette nette ou flux libre n’est déduit.</p>
      {data.liquidity.length ? <details className="my-3"><summary className="cursor-pointer text-signal">Voir les observations ({data.liquidity.length})</summary><div className="mt-3 grid gap-3 md:grid-cols-2">{data.liquidity.map((item) => <article key={item.id} className="rounded border border-white/10 p-3"><p className="text-white">{item.label} : {item.value} {item.unit}</p><p className="mt-2 text-sm">{item.start ? `Du ${item.start} au ${item.end}` : `Solde au ${item.end}`}</p><p className="mt-1 break-words text-xs">{item.concept}</p>{item.stale_period ? <p className="mt-1 text-xs text-amber-300">Date de référence ancienne : plus de 180 jours.</p> : null}<p className="mt-2 text-xs"><a href={item.source_url} target="_blank" rel="noreferrer" className="text-signal underline">Dépôt SEC</a> · déposé le {item.filed}</p></article>)}</div></details> : <p className="my-3 text-sm">Aucune observation dans cette couverture ; cela ne signifie ni trésorerie ni dette nulle.</p>}
      <details className="my-4"><summary className="cursor-pointer text-white">Points et risques à vérifier dans les faits ({data.checks.length})</summary>
        <p className="my-2 text-xs">Questions de recherche ; le type d’un fait ne suffit pas à déterminer son effet favorable ou défavorable.</p>
        {data.checks.map((item) => <article key={item.event_id} className="my-3 border-t border-white/10 pt-3"><p className="text-white">{item.title}</p><p className="my-2 text-sm">{item.label}</p><p className="text-xs text-amber-300">{item.relationship.basis === "security_mention" ? "Mention du titre et de sa cotation" : "Mention de l’émetteur, effet sur ce titre à vérifier"} · rôle : {item.relationship.role}</p>{item.summary ? <p className="mt-2 text-sm">{item.summary}</p> : null}<blockquote className="my-2 border-l-2 border-signal/40 pl-3 text-sm">{item.evidence}</blockquote><Sources sources={item.sources} /><p className="mt-2 text-xs">{item.coverage ? `Couverture du texte : ${Math.round(item.coverage.coverage_ratio * 100)} %. ${item.coverage.document_truncated ? "Document tronqué." : ""}` : "Couverture du texte non documentée."} Vérifier dans le document complet.</p></article>)}
      </details>
      <h3 className="mt-5 text-lg text-white">Prochains événements</h3>
      <p className="my-2 text-xs">Calendrier prévisionnel, horizon de 180 jours. Une consultation n’est pas une publication. Les dates peuvent être modifiées.</p>
      {data.upcoming.length ? data.upcoming.map((item, index) => <article key={`${item.source_url}-${item.report_date}-${index}`} className="my-3 rounded border border-white/10 p-3"><p className="text-white">Résultats à confirmer : {item.report_date}</p><p className="mt-1 text-sm">Fin de période : {item.fiscal_period_end}</p>{item.conflicting_dates ? <p className="mt-1 text-amber-300">Dates contradictoires conservées : vérifier la publication officielle.</p> : null}<p className="mt-2 text-xs"><a href={item.source_url} target="_blank" rel="noreferrer" className="text-signal underline">Source du calendrier</a> · {item.provider} · {item.published_at ? `publié le ${item.published_at}` : "date de publication non fournie"} · consulté le {new Date(item.observed_at).toLocaleString("fr-FR")}</p></article>) : <p className="my-3 text-sm">Aucune date exploitable dans la couverture disponible.</p>}
      <h3 className="mt-5 text-lg text-white">Données manquantes et travail restant</h3>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-sm">{data.missing_data.map((item) => <li key={item}>{item}</li>)}</ul>
    </> : null}
  </section>;
}
