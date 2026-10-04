"use client";

import { useEffect, useRef, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const metrics: Record<string, string> = { revenue: "Chiffre d’affaires", net_income: "Résultat net", eps_basic: "BPA de base", eps_diluted: "BPA dilué" };
type Fact = { id: string; metric: string; concept: string; taxonomy: string; value: string;
  unit: string; start: string; end: string; filed: string; accession: string; form: string;
  filing_period: string | null; fiscal_year: number | null; frame: string | null;
  source_url: string; data_source_url: string; observed_at: string;
  comparison: { status: string; reasons: string[] } | null };
type Results = { items: Fact[]; next_offset: number | null; notice: string;
  available_metrics: string[]; supported_metrics: string[];
  collection: { supported: boolean; cik: string | null; scheduler_enabled: boolean;
    status: string; error: string | null; source_url: string | null; started_at: string | null; fetched_count: number } };
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
    fetch(`${api}/market/instruments/${instrumentId}/financials`, { cache: "no-store", signal: request.signal })
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
      const response = await fetch(`${api}/market/instruments/${instrumentId}/financials?offset=${page}`, { cache: "no-store", signal });
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
      {data.collection.status === "success" ? <p className="my-3 text-xs">Mesures absentes de l’historique conservé : {data.supported_metrics.filter((metric) => !data.available_metrics.includes(metric)).map((metric) => metrics[metric]).join(", ") || "aucune des mesures prises en charge"}.</p> : null}
      <details className="mt-4"><summary className="cursor-pointer text-white">Observations détaillées ({data.items.length} sur cette page)</summary>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="text-slate-400"><th className="p-2">Mesure et définition</th><th className="p-2">Valeur et unité</th><th className="p-2">Période exacte</th><th className="p-2">Dépôt et preuve</th></tr></thead><tbody>{data.items.map((fact) => <tr key={fact.id} className="border-t border-white/10 align-top">
          <td className="p-2">{metrics[fact.metric]}<span className="mt-1 block max-w-72 break-words text-xs text-slate-400">{fact.taxonomy}:{fact.concept}</span></td>
          <td className="whitespace-nowrap p-2">{amount(fact.value)} {fact.unit}</td>
          <td className="whitespace-nowrap p-2">{fact.start} → {fact.end}</td>
          <td className="p-2"><a href={fact.source_url} target="_blank" rel="noreferrer" className="text-signal underline">{fact.form} · déposé le {fact.filed}</a><p className="mt-1 text-xs">Accession : {fact.accession}</p><p className="mt-1 text-xs text-slate-400">Contexte du dépôt : {fact.fiscal_year ?? "année inconnue"} / {fact.filing_period ?? "période inconnue"}. Consultation : {new Date(fact.observed_at).toLocaleString("fr-FR")}.</p>
            {fact.comparison ? <details className="mt-2 text-xs"><summary className="cursor-pointer text-amber-300">Écart aux estimations non calculé</summary><ul className="mt-2 list-disc space-y-1 pl-4">{fact.comparison.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></details> : null}
          </td>
        </tr>)}</tbody></table></div>
        <div className="mt-4 flex gap-5 text-sm text-signal"><button disabled={busy || !offset} onClick={() => void refresh(Math.max(0, offset - 50))} className="disabled:opacity-40">Précédent</button><button disabled={busy || data.next_offset === null} onClick={() => void refresh(data.next_offset ?? offset)} className="disabled:opacity-40">Suivant</button></div>
      </details>
    </> : !error ? <p role="status" className="text-sm">Chargement…</p> : null}
  </section>;
}
