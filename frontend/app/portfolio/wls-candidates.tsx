"use client";

import { apiFetch } from "../lib/api";

import Link from "next/link";
import { Pagination } from "../components/ui";
import { useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";
type Instrument = { id: string; symbol: string; exchange: string; name: string };
type Mapping = { instrument: Instrument; source_url: string; as_of: string; note: string; observed_at: string };
type Row = { bloomberg_identifier: string; source_cell: string; mapping_status: string;
  listing_mapping: Mapping | null; suggested_instrument: Instrument | null;
  identity_observation: { status: string; observed_at: string; source_url: string;
    data: { records?: Array<{ figi: string; name: string | null; securityType: string | null }> } | null } | null;
  automatic_mappings: Array<{ symbol: string; exchange: string; listing_figi: string; identity_observed_at: string }> };
type Snapshot = { loaded: boolean; items: Row[]; total: number; security_count: number;
  mapped_count: number; source_filename: string; source_sheet: string; observed_at: string;
  composition_as_of: string | null; notice: string; origin: string;
  automatic_mapped_count: number; identity_statuses: Record<string, number>;
  archive_history: Array<{ source_hash: string; source_filename: string; security_count: number; observed_at: string }>;
  archive_history_limited: boolean };
const input = "w-full rounded-lg border border-white/15 bg-slate-950 p-2 text-sm text-white";

export function WlsCandidates({ instruments, onRefresh }: { instruments: Instrument[]; onRefresh: () => Promise<void> }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<Snapshot | null>(null);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<Row | null>(null);
  const [instrumentId, setInstrumentId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [batch, setBatch] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    apiFetch(`${api}/market/wls-candidates?search=${encodeURIComponent(query)}&offset=${offset}&limit=10`,
      { signal: controller.signal, cache: "no-store" }).then(async (response) => {
        if (!response.ok) throw new Error("Liste WLS indisponible.");
        return response.json() as Promise<Snapshot>;
      }).then((payload) => { setData(payload); setLoading(false); setError(""); })
      .catch((e) => { if (!controller.signal.aborted) { setError(String(e.message)); setLoading(false); } });
    return () => controller.abort();
  }, [query, offset, revision]);

  return <section className="mt-6 rounded-2xl border border-white/10 p-5">
    <h2 className="font-display text-xl text-white">Liste WLS partielle fournie</h2>
    {error ? <p role="alert" className="mt-3 text-amber-300">{error}</p> : null}
    {message ? <p role="status" className="mt-3 text-sm text-signal">{message}</p> : null}
    {!data ? <p className="mt-3 text-sm">Chargement de la liste…</p> : !data.loaded ?
      <p className="mt-3 text-sm">Aucune préparation WLS chargée.</p> : <>
      <p className="mt-3 text-sm">{data.security_count} titres · {data.mapped_count} correspondances déclarées avec des cotations suivies.</p>
      <p className="mt-2 text-sm">OpenFIGI : {Object.values(data.identity_statuses).reduce((a, b) => a + b, 0)} titres consultés · {data.automatic_mapped_count} cotations suivies résolues automatiquement. La collecte avance en arrière-plan, sans appel LLM.</p>
      <p className="mt-1 text-xs text-slate-400">{Object.entries(data.identity_statuses).map(([status, count]) => `${status} : ${count}`).join(" · ") || "En attente du premier lot"}</p>
      <div className="mt-3 flex gap-4 text-sm text-signal"><button disabled={busy} className="underline disabled:opacity-40" onClick={async () => {
        setBusy(true); setError(""); setMessage("");
        try {
          const response = await apiFetch(`${api}/market/wls-candidates/collect`, { method: "POST" });
          const payload = await response.json();
          if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Collecte indisponible.");
          setMessage(payload.status === "waiting" ? "Une collecte est déjà en cours ou une reprise est planifiée." : payload.status === "failed" ? "Le fournisseur n’a pas répondu correctement ; reprise automatique planifiée." : `Lot terminé : ${payload.attempted} requêtes d’identification.`);
          setRevision((r) => r + 1); await onRefresh();
        } catch (e) { setError(e instanceof Error ? e.message : "Collecte indisponible."); }
        finally { setBusy(false); }
      }}>Traiter le prochain lot</button><button className="underline disabled:opacity-40" disabled={busy} onClick={async () => {
        setRevision((r) => r + 1); try { await onRefresh(); } catch { setError("Actualisation indisponible."); }
      }}>Actualiser la progression</button></div>
      <p className="mt-2 text-sm text-amber-300">{data.notice}</p>
      <p className="mt-2 text-xs text-slate-400">{data.source_filename} · {data.source_sheet} · lecture du {new Date(data.observed_at).toLocaleString("fr-FR")}. Date de composition : {data.composition_as_of ?? "inconnue"}.</p>
      <p className="mt-1 text-xs text-slate-400">{data.origin}</p>
      <form className="mt-4 flex gap-3" onSubmit={(e) => { e.preventDefault(); setLoading(true); setData(null); setOffset(0); setQuery(search.trim()); setRevision(r => r + 1); }}>
        <input aria-label="Rechercher un identifiant Bloomberg" className={input} value={search} maxLength={100}
          onChange={(e) => setSearch(e.target.value)} placeholder="Ex. AAPL US Equity ou 005930" />
        <button className="text-signal underline">Rechercher</button>
      </form>
      <p className="mt-3 text-sm">{data.total} résultat(s)</p>
      <div id="wls-results" className="mt-3 overflow-x-auto"><table className="responsive-table w-full text-left text-sm">
        <thead><tr><th className="p-2">Identifiant Bloomberg</th><th>Cellule source</th><th>Correspondance de cotation</th></tr></thead>
        <tbody>{data.items.map((row) => <tr key={row.bloomberg_identifier} className="border-t border-white/10">
          <td data-label="Identifiant Bloomberg" className="p-2"><div>{row.bloomberg_identifier}</div></td><td data-label="Cellule source"><div>{row.source_cell}</div></td>
          <td data-label="Correspondance de cotation"><div>{row.identity_observation ? <details className="mb-2"><summary>OpenFIGI : {row.identity_observation.status}</summary>
            {row.identity_observation.data?.records?.map((record, index) => <p key={`${record.figi}-${index}`}>{record.name} · {record.figi} · {record.securityType}</p>)}
            <p className="text-xs">Consultation du {new Date(row.identity_observation.observed_at).toLocaleString("fr-FR")}, pas une date de publication.</p>
            <a className="text-signal underline" href="https://www.openfigi.com/api/documentation" target="_blank" rel="noreferrer">Source et méthode OpenFIGI</a>
          </details> : <p className="text-xs">Identification automatique en attente.</p>}
          {row.automatic_mappings.map((mapping) => <p key={mapping.listing_figi} className="text-xs text-signal">Cotation résolue : {mapping.symbol} · {mapping.exchange} · {mapping.listing_figi}</p>)}
          {row.listing_mapping ? <details><summary className={row.mapping_status === "conflict" ? "text-amber-300" : ""}>
            {row.listing_mapping.instrument.symbol} · {row.listing_mapping.instrument.exchange} · {row.mapping_status === "conflict" ? "identité modifiée, à revoir" : "déclarée"}</summary>
            <p>{row.listing_mapping.note}</p><a className="text-signal underline" href={row.listing_mapping.source_url} target="_blank" rel="noreferrer">Source de correspondance du {row.listing_mapping.as_of}</a>
          </details> : <><button className="text-signal underline" onClick={() => {
            setSelected(row); setInstrumentId(row.suggested_instrument?.id ?? ""); requestAnimationFrame(() => document.getElementById("wls-mapping")?.scrollIntoView({ behavior: "smooth" }));
          }}>Documenter la correspondance</button>
            {row.suggested_instrument ? <span className="block text-xs">Identifiant Bloomberg déjà déclaré sur {row.suggested_instrument.symbol} · {row.suggested_instrument.exchange} ; preuve à fournir.</span> : null}</>}
          </div></td></tr>)}</tbody></table></div>
      <Pagination page={offset / 10} pageSize={10} total={data.total} busy={loading} onChange={p => { setLoading(true); setData(null); setOffset(p * 10); }} label="titres WLS" targetId="wls-results" />
      <p className="mt-3 text-sm"><Link className="text-signal underline" href="/international">Ajouter une cotation internationale documentée</Link></p>
      <details className="mt-4 text-sm"><summary>Historique des fichiers WLS</summary>
        <p>Chaque fichier reste une liste déclarée. Les différences entre exports ne prouvent pas les dates d’entrée ou de sortie de l’indice.</p>
        {data.archive_history.map((archive) => <p key={archive.source_hash}>{archive.source_filename} · {archive.security_count} titres · archivage de l’instantané consulté le {new Date(archive.observed_at).toLocaleString("fr-FR")}</p>)}
        {!data.archive_history.length ? <p>Aucun ancien fichier.</p> : null}
        {data.archive_history_limited ? <p>Les dix derniers fichiers sont affichés ; les autres restent conservés.</p> : null}
      </details>
      <details className="mt-4 text-sm"><summary>Importer des correspondances documentées en lot</summary>
        <p>Coller un objet JSON avec une liste « items » (100 maximum). Chaque ligne contient bloomberg_identifier, instrument_id, source_url, as_of, note et correspondence_confirmed=true. Les succès sont conservés ; chaque rejet est signalé.</p>
        <textarea className={`${input} mt-2`} aria-label="Correspondances JSON" rows={5} value={batch} onChange={(e) => setBatch(e.target.value)} />
        <button className="mt-2 text-signal underline disabled:opacity-40" disabled={busy || !batch.trim()} onClick={async () => {
          setBusy(true); setError(""); setMessage("");
          try {
            const body = JSON.parse(batch);
            const response = await apiFetch(`${api}/market/wls-candidates/mappings/batch`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
            const payload = await response.json();
            if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Lot invalide : vérifier les champs, sources et dates.");
            setMessage(`${payload.saved} correspondance(s) conservée(s). ` + payload.items.filter((r: { status: string }) => r.status === "rejected").map((r: { bloomberg_identifier: string; reason: string }) => `${r.bloomberg_identifier} : ${r.reason}`).join(" ; "));
            setRevision((r) => r + 1); await onRefresh();
          } catch (e) { setError(e instanceof Error ? e.message : "Lot invalide."); }
          finally { setBusy(false); }
        }}>Importer le lot</button>
      </details>
    </>}
    {selected ? <form id="wls-mapping" key={selected.bloomberg_identifier} className="mt-5 grid gap-3 rounded-lg border border-white/15 p-4" onSubmit={async (event) => {
      event.preventDefault(); const form = new FormData(event.currentTarget);
      setBusy(true); setError("");
      try {
        const response = await apiFetch(`${api}/market/wls-candidates/mappings`, { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({
            bloomberg_identifier: selected.bloomberg_identifier, instrument_id: instrumentId,
            source_url: form.get("source_url"), as_of: form.get("as_of"), note: form.get("note"),
            correspondence_confirmed: form.get("confirmed") === "on",
          }) });
        const payload = await response.json();
        if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Vérifie les champs et la date de la source.");
        setSelected(null); setRevision((r) => r + 1);
      } catch (e) { setError(e instanceof Error ? e.message : "Enregistrement impossible."); }
      finally { setBusy(false); }
    }}>
      <h3 className="text-white">Rapprocher {selected.bloomberg_identifier}</h3>
      <label className="text-sm">Cotation suivie<select aria-label="Cotation suivie" className={input} value={instrumentId} required onChange={(e) => setInstrumentId(e.target.value)}>
        <option value="">Choisir le titre et le marché exacts</option>{instruments.map((i) => <option key={i.id} value={i.id}>{i.symbol} · {i.exchange} · {i.name}</option>)}
      </select></label>
      <label className="text-sm">URL de preuve de correspondance<input className={input} type="url" name="source_url" required /></label>
      <label className="text-sm">Date de la source de correspondance<input className={input} type="date" name="as_of" required /></label>
      <label className="text-sm">Justification du titre, de sa classe et de sa cotation<textarea className={input} name="note" minLength={20} maxLength={1500} required /></label>
      <label className="text-sm"><input type="checkbox" name="confirmed" required /> Je confirme que la preuve concerne ce titre et cette cotation, pas seulement son émetteur.</label>
      <p className="text-xs text-amber-300">La saisie ne certifie pas la preuve et ne date pas la composition WLS.</p>
      <div className="flex gap-4"><button disabled={busy} className="text-signal underline disabled:opacity-40">Enregistrer</button>
        <button type="button" disabled={busy} onClick={() => setSelected(null)}>Annuler</button></div>
    </form> : null}
  </section>;
}
