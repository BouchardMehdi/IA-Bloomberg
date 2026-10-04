"use client";

import { useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Reference = { value: string; label: string; rationale: string; as_of: string; source_url: string; published_at: string };
type Observation = { id: string; observed_at: string; valuation_date: string; eps_per_security: string;
  currency: string; period_start: string; period_end: string; source_url: string; published_at: string;
  security_source_url: string; security_published_at: string; security_basis_note: string; reference: Reference | null };
type Data = { notice: string; instrument: { currency: string; quote_multiplier: string };
  price: { close: string; date: string; source_url: string } | null; observation: Observation | null;
  history: Observation[]; history_limited: boolean;
  calculation: { status: string; reasons: string[]; pe: string | null; earnings_yield_percent: string | null;
    normalized_price: string | null; reference_comparison: { position: string; difference_percent: string;
      reference: Reference; notice: string } | null } };
function Field({ name, label, type = "text", value, required = true }: { name: string; label: string; type?: string; value?: string; required?: boolean }) {
  return <label className="block text-sm">{label}<input name={name} type={type} defaultValue={value} required={required} step={type === "number" ? "any" : undefined} className="mt-1 block w-full rounded border border-white/20 bg-slate-950 p-2" /></label>;
}
export function Valuation({ instrumentId }: { instrumentId: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const [withReference, setWithReference] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${api}/market/instruments/${instrumentId}/valuation`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error("Valorisation indisponible."); return response.json() as Promise<Data>; })
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [instrumentId, revision]);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!data) return;
    setBusy(true); setError(""); setMessage("");
    const form = new FormData(event.currentTarget);
    const value = (key: string) => String(form.get(key) ?? "");
    const timestamp = (key: string) => new Date(value(key)).toISOString();
    try {
      const body = { valuation_date: value("valuation_date"), currency: data.instrument.currency,
        quote_multiplier: data.instrument.quote_multiplier, period_start: value("period_start"),
        period_end: value("period_end"), period_type: "annual", basis: "gaap_diluted",
        eps_per_security: value("eps"), source_url: value("source"), published_at: timestamp("published"),
        security_basis_confirmed: form.get("confirmed") === "on", security_basis_note: value("note"),
        security_source_url: value("security_source"), security_published_at: timestamp("security_published"),
        reference: withReference ? { value: value("reference_value"), label: value("reference_label"),
          rationale: value("reference_rationale"), basis: "annual_gaap_diluted",
          as_of: value("reference_date"), source_url: value("reference_source"),
          published_at: timestamp("reference_published") } : null };
      const response = await fetch(`${api}/market/instruments/${instrumentId}/valuation`, { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Saisie incompatible : vérifier dates, sources, période annuelle et conventions.");
      setMessage(result.inserted ? "Observation conservée. Le calcul reste soumis aux contrôles de compatibilité." : "Observation déjà conservée, sans doublon.");
      setRevision((n) => n + 1);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="my-5 rounded-xl border border-white/10 p-5">
    <div className="flex flex-wrap justify-between gap-3"><h2 className="text-xl text-white">Valorisation : prix rapporté aux bénéfices</h2><button disabled={busy} className="text-sm text-signal underline" onClick={() => { setError(""); setRevision((n) => n + 1); }}>Actualiser</button></div>
    {error ? <p role="alert" className="my-3 text-rose-300">{error}</p> : null}
    {message ? <p role="status" className="my-3 text-signal">{message}</p> : null}
    {!data && !error ? <p role="status" className="mt-3">Chargement…</p> : null}
    {data ? <><p className="my-3 text-sm">{data.notice}</p>
      {data.calculation.reference_comparison ? <p className="my-2 text-xs">Date de la référence fournie : {data.calculation.reference_comparison.reference.as_of}. Les dates de cours et de référence peuvent différer de trente jours maximum.</p> : null}
      {data.price ? <p className="my-3 text-sm">Clôture brute : {data.price.close} × {data.instrument.quote_multiplier} {data.instrument.currency} · séance du {data.price.date} · <a href={data.price.source_url} target="_blank" rel="noreferrer" className="text-signal underline">Source du cours</a></p> : <p className="my-3">Cours manquant.</p>}
      {data.calculation.status === "available" ? <><p className="my-3 text-lg text-white">PER annuel : {data.calculation.pe} fois les bénéfices · rendement bénéficiaire comptable : {data.calculation.earnings_yield_percent} %</p>{data.calculation.reference_comparison ? <div className="my-3 text-sm"><p>Multiple {data.calculation.reference_comparison.position === "higher" ? "supérieur" : data.calculation.reference_comparison.position === "lower" ? "inférieur" : "égal"} à « {data.calculation.reference_comparison.reference.label} » ({data.calculation.reference_comparison.reference.value}) · écart {data.calculation.reference_comparison.difference_percent} %.</p><p className="mt-2">{data.calculation.reference_comparison.notice}</p><a href={data.calculation.reference_comparison.reference.source_url} target="_blank" rel="noreferrer" className="text-signal underline">Référence fournie</a><p className="mt-1 text-xs">Justification : {data.calculation.reference_comparison.reference.rationale} · publié le {data.calculation.reference_comparison.reference.published_at}</p></div> : <p className="my-3 text-sm text-amber-300">Référence comparable manquante : impossible de qualifier le multiple d’élevé ou faible.</p>}</> : <><p className="my-3 text-amber-300">Calcul bloqué</p><ul className="list-disc space-y-2 pl-5 text-sm">{data.calculation.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></>}
      {data.observation ? <div className="my-4 text-sm"><p>BPA annuel dilué fourni : {data.observation.eps_per_security} {data.observation.currency} par titre · {data.observation.period_start} → {data.observation.period_end}.</p><p className="mt-2"><a href={data.observation.source_url} target="_blank" rel="noreferrer" className="text-signal underline">Source du résultat</a> · publié le {data.observation.published_at}</p><p className="mt-2"><a href={data.observation.security_source_url} target="_blank" rel="noreferrer" className="text-signal underline">Preuve de correspondance au titre</a> · publié le {data.observation.security_published_at}</p><p className="mt-2 text-xs">{data.observation.security_basis_note} · consultation : {new Date(data.observation.observed_at).toLocaleString("fr-FR")}</p></div> : null}
      <details className="my-4"><summary className="cursor-pointer text-white">Fournir les données nécessaires à la valorisation</summary><p className="my-3 text-sm">BPA annuel GAAP dilué, déjà ramené à un titre de cette cotation, en {data.instrument.currency}. Justifier les classes d’actions, ADR et ajustements de divisions d’actions. Une simple association au CIK ne suffit pas. Les sources doivent être publiées avant le jour de la séance. Aucun BPA trimestriel n’est annualisé.</p>
        <form onSubmit={(event) => void save(event)} className="grid gap-3 md:grid-cols-2">
          <Field name="valuation_date" label="Séance couverte par les preuves" type="date" value={data.price?.date} />
          <Field name="eps" label={`BPA annuel dilué par titre (${data.instrument.currency})`} type="number" />
          <Field name="period_start" label="Début de période annuelle" type="date" /><Field name="period_end" label="Fin de période annuelle" type="date" />
          <Field name="source" label="URL du résultat annuel" type="url" /><Field name="published" label="Publication du résultat (heure locale)" type="datetime-local" />
          <Field name="security_source" label="URL de preuve pour ce titre et ses ajustements" type="url" /><Field name="security_published" label="Publication de cette preuve (heure locale)" type="datetime-local" />
          <label className="block text-sm md:col-span-2">Explication de la correspondance et des ajustements<textarea name="note" required minLength={20} maxLength={1500} className="mt-1 block w-full rounded border border-white/20 bg-slate-950 p-2" /></label>
          <label className="text-sm md:col-span-2"><input type="checkbox" name="confirmed" required className="mr-2" />Je confirme que le BPA correspond à un titre de cette cotation, avec les ajustements nécessaires à la séance indiquée.</label>
          <label className="text-sm md:col-span-2"><input type="checkbox" checked={withReference} onChange={(e) => setWithReference(e.target.checked)} className="mr-2" />Ajouter un PER de référence comparable (annuel GAAP dilué, daté de moins de 30 jours)</label>
          {withReference ? <><Field name="reference_value" label="PER de référence" type="number" /><Field name="reference_label" label="Nom et périmètre de la référence" /><Field name="reference_date" label="Date de référence" type="date" /><Field name="reference_source" label="URL de la référence" type="url" /><Field name="reference_published" label="Publication de la référence (heure locale)" type="datetime-local" /><Field name="reference_rationale" label="Pourquoi cette référence est comparable" /></> : null}
          <button disabled={busy} className="rounded border border-signal/40 px-3 py-2 text-signal disabled:opacity-40 md:col-span-2">{busy ? "Enregistrement…" : "Conserver l’observation sourcée"}</button>
        </form>
      </details>
      <details className="my-3"><summary className="cursor-pointer text-white">Historique des observations ({data.history.length} dernières)</summary><ul className="mt-3 space-y-2 text-sm">{data.history.map((item) => <li key={item.id}>Séance {item.valuation_date} · BPA {item.eps_per_security} {item.currency} · période {item.period_start} → {item.period_end} · <a href={item.source_url} target="_blank" rel="noreferrer" className="text-signal underline">Source</a> · publié le {item.published_at} · consulté le {new Date(item.observed_at).toLocaleString("fr-FR")}</li>)}</ul>{data.history_limited ? <p className="mt-2 text-xs">Affichage limité aux vingt dernières observations ; les précédentes restent conservées.</p> : null}</details>
    </> : null}
  </section>;
}
