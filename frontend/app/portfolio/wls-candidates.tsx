"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Instrument = { id: string; symbol: string; exchange: string; name: string };
type Mapping = { instrument: Instrument; source_url: string; as_of: string; note: string; observed_at: string };
type Row = { bloomberg_identifier: string; source_cell: string; mapping_status: string;
  listing_mapping: Mapping | null; suggested_instrument: Instrument | null };
type Snapshot = { loaded: boolean; items: Row[]; total: number; security_count: number;
  mapped_count: number; source_filename: string; source_sheet: string; observed_at: string;
  composition_as_of: string | null; notice: string; origin: string };
const input = "w-full rounded-lg border border-white/15 bg-slate-950 p-2 text-sm text-white";

export function WlsCandidates({ instruments }: { instruments: Instrument[] }) {
  const [data, setData] = useState<Snapshot | null>(null);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<Row | null>(null);
  const [instrumentId, setInstrumentId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${api}/market/wls-candidates?search=${encodeURIComponent(query)}&offset=${offset}&limit=50`,
      { signal: controller.signal, cache: "no-store" }).then(async (response) => {
        if (!response.ok) throw new Error("Liste WLS indisponible.");
        return response.json() as Promise<Snapshot>;
      }).then((payload) => { setData(payload); setError(""); })
      .catch((e) => { if (!controller.signal.aborted) setError(String(e.message)); });
    return () => controller.abort();
  }, [query, offset, revision]);

  return <section className="mt-6 rounded-2xl border border-white/10 p-5">
    <h2 className="font-display text-xl text-white">Liste WLS partielle fournie</h2>
    {error ? <p role="alert" className="mt-3 text-amber-300">{error}</p> : null}
    {!data ? <p className="mt-3 text-sm">Chargement de la liste…</p> : !data.loaded ?
      <p className="mt-3 text-sm">Aucune préparation WLS chargée.</p> : <>
      <p className="mt-3 text-sm">{data.security_count} titres · {data.mapped_count} correspondances déclarées avec des cotations suivies.</p>
      <p className="mt-2 text-sm text-amber-300">{data.notice}</p>
      <p className="mt-2 text-xs text-slate-400">{data.source_filename} · {data.source_sheet} · lecture du {new Date(data.observed_at).toLocaleString("fr-FR")}. Date de composition : {data.composition_as_of ?? "inconnue"}.</p>
      <p className="mt-1 text-xs text-slate-400">{data.origin}</p>
      <form className="mt-4 flex gap-3" onSubmit={(e) => { e.preventDefault(); setOffset(0); setQuery(search.trim()); }}>
        <input aria-label="Rechercher un identifiant Bloomberg" className={input} value={search} maxLength={100}
          onChange={(e) => setSearch(e.target.value)} placeholder="Ex. AAPL US Equity ou 005930" />
        <button className="text-signal underline">Rechercher</button>
      </form>
      <p className="mt-3 text-sm">{data.total} résultat(s)</p>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm">
        <thead><tr><th className="p-2">Identifiant Bloomberg</th><th>Cellule source</th><th>Correspondance de cotation</th></tr></thead>
        <tbody>{data.items.map((row) => <tr key={row.bloomberg_identifier} className="border-t border-white/10">
          <td className="p-2">{row.bloomberg_identifier}</td><td>{row.source_cell}</td>
          <td>{row.listing_mapping ? <details><summary className={row.mapping_status === "conflict" ? "text-amber-300" : ""}>
            {row.listing_mapping.instrument.symbol} · {row.listing_mapping.instrument.exchange} · {row.mapping_status === "conflict" ? "identité modifiée, à revoir" : "déclarée"}</summary>
            <p>{row.listing_mapping.note}</p><a className="text-signal underline" href={row.listing_mapping.source_url} target="_blank" rel="noreferrer">Source de correspondance du {row.listing_mapping.as_of}</a>
          </details> : <><button className="text-signal underline" onClick={() => {
            setSelected(row); setInstrumentId(row.suggested_instrument?.id ?? "");
          }}>Documenter la correspondance</button>
            {row.suggested_instrument ? <span className="block text-xs">Identifiant Bloomberg déjà déclaré sur {row.suggested_instrument.symbol} · {row.suggested_instrument.exchange} ; preuve à fournir.</span> : null}</>}
          </td></tr>)}</tbody></table></div>
      <div className="mt-4 flex gap-4 text-sm text-signal">
        <button disabled={offset === 0} className="disabled:opacity-40" onClick={() => setOffset(Math.max(0, offset - 50))}>Précédent</button>
        <button disabled={offset + 50 >= data.total} className="disabled:opacity-40" onClick={() => setOffset(offset + 50)}>Suivant</button>
      </div>
      <p className="mt-3 text-sm"><Link className="text-signal underline" href="/international">Ajouter une cotation internationale documentée</Link></p>
    </>}
    {selected ? <form key={selected.bloomberg_identifier} className="mt-5 grid gap-3 rounded-lg border border-white/15 p-4" onSubmit={async (event) => {
      event.preventDefault(); const form = new FormData(event.currentTarget);
      setBusy(true); setError("");
      try {
        const response = await fetch(`${api}/market/wls-candidates/mappings`, { method: "POST",
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
      <label className="text-sm">Cotation suivie<select className={input} value={instrumentId} required onChange={(e) => setInstrumentId(e.target.value)}>
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
