"use client";

import { apiFetch } from "../lib/api";

import { useEffect, useRef, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";
type Status = { supported: boolean; cik: string | null; scheduler_enabled: boolean;
  source_url: string | null; status: string; started_at: string | null;
  fetched_count: number; inserted_count: number; error: string | null; notice: string };
const labels: Record<string, string> = { pending: "Pas encore consulté", running: "Collecte en cours",
  success: "Collecte réussie", failed: "Échec de collecte" };

export function CompanyPublications({ instrumentId, onCollected }: { instrumentId: string; onCollected: () => void }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    apiFetch(`${api}/market/instruments/${instrumentId}/publications/collection`, { cache: "no-store", signal: request.signal })
      .then(async (response) => { if (!response.ok) throw new Error("État de collecte indisponible."); return response.json() as Promise<Status>; })
      .then((data) => { if (!request.signal.aborted) setStatus(data); })
      .catch((e: Error) => { if (!request.signal.aborted) setError(e.message); });
    return () => request.abort();
  }, [instrumentId]);
  async function collect() {
    const signal = controller.current?.signal; setBusy(true); setError(""); setMessage("");
    try {
      const response = await apiFetch(`${api}/market/instruments/${instrumentId}/publications/collect`, { method: "POST", signal });
      if (!response.ok) throw new Error("Impossible de collecter les publications.");
      const result = await response.json() as { status: string; error?: string; inserted?: number };
      if (signal?.aborted) return;
      const messages: Record<string, string> = { success: `Collecte réussie · ${result.inserted ?? 0} nouveau(x) document(s). Le rapprochement sera effectué par le pipeline lors du prochain cycle (environ une minute).`,
        failed: `Collecte échouée (${result.error ?? "erreur"}). L’historique est conservé.`,
        cached_or_retry_pending: "Déjà consulté récemment ou reprise en attente. Succès : cache d’une heure ; erreur : cinq minutes.",
        collection_in_progress: "Une collecte SEC ciblée est déjà en cours. Réessaie dans quelques instants.",
        unsupported_identity: "Aucun CIK vérifié disponible pour cet émetteur." };
      setMessage(messages[result.status] ?? result.status);
      const updated = await apiFetch(`${api}/market/instruments/${instrumentId}/publications/collection`, { cache: "no-store", signal });
      if (!updated.ok) throw new Error("État de collecte indisponible.");
      const data = await updated.json() as Status;
      if (!signal?.aborted) { setStatus(data); if (result.status === "success") onCollected(); }
    } catch (e) { if (!signal?.aborted) setError((e as Error).message); }
    finally { if (!signal?.aborted) setBusy(false); }
  }
  return <section className="my-5 rounded-xl border border-white/10 p-5">
    <h2 className="text-xl text-white">Publications officielles de l’émetteur</h2>
    <p className="my-2 text-sm">Collecte ciblée SEC par CIK : 8-K, 10-Q, 10-K, 6-K, 20-F, 40-F et amendements. Sans appel LLM supplémentaire ni consommation du quota Alpha Vantage. Un dépôt reste une publication à examiner.</p>
    {status ? <>
      <p className="text-sm">{status.supported ? `CIK ${status.cik} · ${labels[status.status] ?? status.status}` : "CIK vérifié absent : sociétés hors SEC non couvertes par ce collecteur."}</p>
      {status.started_at ? <p className="mt-2 text-sm">Dernière tentative : {new Date(status.started_at).toLocaleString("fr-FR")} · {status.fetched_count} document(s) retenu(s), {status.inserted_count} nouveau(x). {status.error ?? ""}</p> : null}
      <p className="mt-2 text-xs">{status.notice} {status.scheduler_enabled ? "Scheduler activé : passage toutes les quinze minutes, par lots de cinq émetteurs." : "Scheduler désactivé : consultation manuelle disponible."}</p>
      {status.source_url ? <a href={status.source_url} target="_blank" rel="noreferrer" className="mt-2 block text-sm text-signal underline">Source du catalogue SEC</a> : null}
      <button onClick={() => void collect()} disabled={busy || !status.supported} className="mt-3 rounded border border-signal/40 px-3 py-2 text-signal disabled:opacity-40">{busy ? "Collecte…" : "Collecter les publications SEC"}</button>
    </> : <p className="text-sm">Chargement de l’état…</p>}
    {error ? <p role="alert" className="mt-3 text-sm text-rose-300">{error}</p> : null}
    {message ? <p role="status" className="mt-3 text-sm text-signal">{message}</p> : null}
    <p className="mt-3 text-xs">Le texte intégral est récupéré séparément selon les limites de taille et d’accès. Les sociétés sans CIK et les publications diffusées uniquement ailleurs restent à raccorder à une source autorisée.</p>
  </section>;
}
