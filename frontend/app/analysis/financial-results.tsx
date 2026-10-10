"use client";

import { Pagination } from "../components/ui";
import { useEffect, useRef, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Fact = { id: string; metric: string; concept: string; taxonomy: string; value: string;
  unit: string; start: string | null; end: string; filed: string; accession: string; form: string;
  filing_period: string | null; fiscal_year: number | null; frame: string | null;
  source_url: string; data_source_url: string; observed_at: string;
  comparison: { status: string; reasons: string[] } | null };
type Results = { items: Fact[]; next_offset: number | null; notice: string;
  available_metrics: string[]; supported_metrics: string[]; metric_labels: Record<string, string>;
  collection: { supported: boolean; cik: string | null; scheduler_enabled: boolean;
    status: string; coverage_current: boolean; error: string | null; source_url: string | null; started_at: string | null; fetched_count: number } };
function amount(value: string) {
  const [integer, fraction] = value.split(".");
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f") + (fraction ? `,${fraction}` : "");
}
const statusLabels: Record<string, string> = { pending: "Pas encore consulté", running: "Collecte en cours", success: "Collecte réussie", failed: "Échec de collecte" };

export function FinancialResults({ instrumentId }: { instrumentId: string }) {
  const [data, setData] = useState<Results | null>(null);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    fetch(`${api}/market/instruments/${instrumentId}/financials?limit=10`, { cache: "no-store", signal: request.signal })
      .then(async (response) => { if (!response.ok) throw new Error("Données financières indisponibles."); return response.json() as Promise<Results>; })
      .then((result) => { if (!request.signal.aborted) setData(result); })
      .catch((e: Error) => { if (!request.signal.aborted) setError(e.message); });
    return () => request.abort();
  }, [instrumentId]);
  async function refresh(page: number, collect = false) {
    const signal = controller.current?.signal; setBusy(true); setError(""); setMessage("");
    try {
      if (collect) {
        const response = await fetch(`${api}/market/instruments/${instrumentId}/financials/collect`, { method: "POST", signal });
        if (!response.ok) throw new Error("Collecte des données financières indisponible.");
        const result = await response.json() as { status: string; inserted?: number; error?: string };
        if (signal?.aborted) return;
        const labels: Record<string, string> = { success: `Collecte réussie · ${result.inserted ?? 0} nouvelle(s) observation(s).`,
          cached_or_retry_pending: "Déjà consulté récemment ou reprise en attente. Cache : 24 heures après succès ; cinq minutes après erreur.",
          collection_in_progress: "Une collecte ciblée SEC est déjà en cours. Réessaie dans quelques instants.",
          failed: `Collecte échouée (${result.error ?? "erreur"}). L’historique est conservé.`, unsupported_identity: "Aucun CIK vérifié disponible." };
        setMessage(labels[result.status] ?? result.status);
      }
      const response = await fetch(`${api}/market/instruments/${instrumentId}/financials?limit=10&offset=${page}`, { cache: "no-store", signal });
      if (!response.ok) throw new Error("Données financières indisponibles.");
      const result = await response.json() as Results;
      if (!signal?.aborted) { setData(result); setOffset(page); }
    } catch (e) { if (!signal?.aborted) setError((e as Error).message); }
    finally { if (!signal?.aborted) setBusy(false); }
  }
  return <section className="my-5 rounded-xl border border-white/10 p-5">
    <h2 className="text-xl text-white">Chiffres financiers publiés — SEC XBRL</h2>
    <p className="my-3 text-sm">Mesures de l’émetteur issues des dépôts US-GAAP. Les périodes cumulées, définitions différentes et valeurs republiées restent séparées. Aucun montant manquant n’est remplacé par zéro et aucun chiffre n’est converti en USD automatiquement.</p>
    {error ? <p role="alert" className="my-3 text-rose-300">{error}</p> : null}
    {message ? <p role="status" className="my-3 text-sm text-signal">{message}</p> : null}
    {data ? <>
      <p className="text-sm">{data.collection.supported ? `CIK ${data.collection.cik} · ${statusLabels[data.collection.status] ?? data.collection.status}` : "Aucun CIK vérifié : collecte SEC indisponible."} {data.collection.error ?? ""}</p>
      {data.collection.started_at ? <p className="mt-2 text-xs">Dernière consultation : {new Date(data.collection.started_at).toLocaleString("fr-FR")} · {data.collection.fetched_count} observation(s) retenue(s).</p> : null}
      <p className="mt-2 text-xs">{data.notice} {data.collection.scheduler_enabled ? "Collecte automatique activée, cache de 24 heures." : "Collecte automatique désactivée."}</p>
      <div className="my-3 flex flex-wrap gap-4 text-sm"><button disabled={busy || !data.collection.supported} onClick={() => void refresh(0, true)} className="rounded border border-signal/40 px-3 py-2 text-signal disabled:opacity-40">{busy ? "Chargement…" : "Collecter les chiffres SEC"}</button><button disabled={busy} onClick={() => void refresh(offset)} className="text-signal underline disabled:opacity-40">Actualiser l’affichage</button>{data.collection.source_url ? <a href={data.collection.source_url} target="_blank" rel="noreferrer" className="text-signal underline">Source des données XBRL</a> : null}</div>
      {!data.items.length ? <p className="text-sm">Aucune observation sur cette page. Cela ne prouve ni l’absence de résultats ni un montant nul.</p> : null}
      {!data.collection.coverage_current && data.collection.supported ? <p className="my-3 text-xs text-amber-300">La nouvelle couverture trésorerie et dette n’a pas encore été consultée. Utilise le bouton de collecte ou attends le passage automatique.</p> : null}
      {data.collection.status === "success" ? <p className="my-3 text-xs">Mesures absentes de l’historique conservé : {data.supported_metrics.filter((metric) => !data.available_metrics.includes(metric)).map((metric) => data.metric_labels[metric] ?? metric).join(", ") || "aucune des mesures prises en charge"}.</p> : null}
      <details id="financial-observations" className="mt-4"><summary className="cursor-pointer text-white">Observations détaillées ({data.items.length} sur cette page)</summary>
        <div className="mt-3 overflow-x-auto"><table className="responsive-table w-full text-left text-sm"><thead><tr className="text-slate-400"><th className="p-2">Mesure et définition</th><th className="p-2">Valeur et unité</th><th className="p-2">Période exacte</th><th className="p-2">Dépôt et preuve</th></tr></thead><tbody>{data.items.map((fact) => <tr key={fact.id} className="border-t border-white/10 align-top">
          <td data-label="Mesure et définition" className="p-2"><div>{data.metric_labels[fact.metric] ?? fact.metric}<span className="mt-1 block max-w-72 break-words text-xs text-slate-400">{fact.taxonomy}:{fact.concept}</span></div></td>
          <td data-label="Valeur et unité" className="p-2"><div>{amount(fact.value)} {fact.unit}</div></td>
          <td data-label="Période exacte" className="p-2"><div>{fact.start ? `${fact.start} → ${fact.end}` : `Solde au ${fact.end}`}</div></td>
          <td data-label="Dépôt et preuve" className="p-2"><div><a href={fact.source_url} target="_blank" rel="noreferrer" className="text-signal underline">{fact.form} · déposé le {fact.filed}</a><p className="mt-1 text-xs">Accession : {fact.accession}</p><p className="mt-1 text-xs text-slate-400">Contexte du dépôt : {fact.fiscal_year ?? "année inconnue"} / {fact.filing_period ?? "période inconnue"}. Consultation : {new Date(fact.observed_at).toLocaleString("fr-FR")}.</p>
            {fact.comparison ? <details className="mt-2 text-xs"><summary className="cursor-pointer text-amber-300">Écart aux estimations non calculé</summary><ul className="mt-2 list-disc space-y-1 pl-4">{fact.comparison.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></details> : null}
          </div></td>
        </tr>)}</tbody></table></div>
        <Pagination page={offset / 10} pageSize={10} hasNext={data.next_offset !== null} busy={busy} onChange={p => void refresh(p * 10)} label="observations financières" targetId="financial-observations" />
      </details>
    </> : !error ? <p role="status" className="text-sm">Chargement…</p> : null}
  </section>;
}
