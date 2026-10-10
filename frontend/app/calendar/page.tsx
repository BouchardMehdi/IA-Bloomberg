"use client";

import Link from "next/link";
import { PageHeader, Pagination } from "../components/ui";
import { useEffect, useState, type FormEvent } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Instrument = { id: string; symbol: string; exchange: string; name: string };
type Observation = { id: string; kind: "schedule" | "estimate" | "reported"; provider: string;
  report_date: string; fiscal_period_end: string; period_type: string; basis: string;
  eps: string | null; currency: string | null; source_url: string;
  time_of_day?: string | null;
  published_at: string | null; observed_at: string;
  comparison?: { status: string; reason?: string; delta?: string; percent?: string | null;
    estimate_source?: string; estimate_published_at?: string; notice?: string } };
type Calendar = { items: Observation[]; next_offset: number | null; notice: string;
  collection: { configured: boolean; supported: boolean; status: string;
    started_at: string | null; error_code: string | null; retry_at: string | null } };
const dateTime = (value: string) => new Date(value).toLocaleString("fr-FR");
const labels = { schedule: "Date prévue", estimate: "Estimation de BPA", reported: "BPA publié fourni" };
const bases: Record<string, string> = { unknown: "Convention inconnue", gaap_basic: "GAAP de base", gaap_diluted: "GAAP dilué", adjusted_basic: "Ajusté de base", adjusted_diluted: "Ajusté dilué" };
const periods: Record<string, string> = { unknown: "Périodicité inconnue", quarterly: "Trimestriel", annual: "Annuel" };
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${api}/market${path}`, { cache: "no-store", ...options });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(typeof payload.detail === "string" ? payload.detail : "Données invalides ou service indisponible. Vérifie les dates, la source et le BPA.");
  }
  return response.json();
}

export default function CalendarPage() {
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [selected, setSelected] = useState("");
  const [data, setData] = useState<Calendar | null>(null);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [kind, setKind] = useState<Observation["kind"]>("schedule");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    request<{ items: Instrument[] }>("/instruments", { signal: controller.signal }).then((result) => {
      setInstruments(result.items); setSelected(result.items[0]?.id ?? "");
      if (!result.items.length) setLoading(false);
    }).catch((e: Error) => { if (!controller.signal.aborted) { setError(e.message); setLoading(false); } });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    request<Calendar>(`/instruments/${selected}/earnings?limit=10&offset=${offset}`, { signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) { setData(result); setLoading(false); } })
      .catch((e: Error) => { if (!controller.signal.aborted) { setError(e.message); setLoading(false); } });
    return () => controller.abort();
  }, [selected, offset, revision]);
  function reload() { setLoading(true); setData(null); setRevision((value) => value + 1); }
  function page(next: number) { setLoading(true); setData(null); setError(""); setOffset(next); }
  async function collect() {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await request<{ status: string; inserted?: number }>(`/instruments/${selected}/earnings/collect`, { method: "POST" });
      const statuses: Record<string, string> = { success: "Collecte terminée", failed: "Collecte échouée : les observations précédentes sont conservées", budget_exhausted: "Quota quotidien partagé épuisé", calendar_budget_exhausted: "Budget du calendrier épuisé pour aujourd’hui", provider_cooldown: "Fournisseur en attente après dépassement de quota", cached_or_retry_pending: "Déjà consulté aujourd’hui ou nouvelle tentative en attente", unsupported_listing: "Cotation non prise en charge" };
      setMessage(`${statuses[result.status] ?? result.status}${result.inserted !== undefined ? ` · ${result.inserted} nouvelle(s) observation(s)` : ""}.`);
      reload();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget;
    const values = new FormData(form); setBusy(true); setError(""); setMessage("");
    try {
      const payload = { kind, fiscal_period_end: values.get("period"), report_date: values.get("report"),
        period_type: values.get("period_type"), source_url: values.get("source"),
        published_at: new Date(String(values.get("published"))).toISOString(),
        ...(kind !== "schedule" ? { eps: values.get("eps"), currency: String(values.get("currency")).toUpperCase(), basis: values.get("basis") } : {}) };
      const result = await request<{ inserted: boolean }>(`/instruments/${selected}/earnings`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setMessage(result.inserted ? "Observation conservée avec sa source." : "Cette observation existe déjà.");
      setOffset(0); reload(); form.reset(); setKind("schedule");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const field = "mt-1 block w-full rounded border border-white/20 bg-slate-950 p-2";
  return <main className="mx-auto max-w-5xl px-5 py-8 text-slate-300">
    <PageHeader title="Calendrier des résultats" description="Retrouvez les dates prévues, les estimations et les résultats publiés pour chaque titre suivi." />
    <p className="mb-4 text-sm leading-6">Dates prévisionnelles à confirmer dans les publications officielles. Les estimations sont séparées des chiffres publiés. Une date passée ne prouve pas que les résultats sont sortis. Les informations de l’émetteur ne prouvent pas l’éligibilité WLS de ce titre.</p>
    {error ? <p role="alert" className="my-3 text-rose-300">{error}</p> : null}
    {message ? <p role="status" className="my-3 text-signal">{message}</p> : null}
    {instruments.length ? <label>Titre suivi<select aria-label="Titre suivi" disabled={busy} className={field} value={selected} onChange={(event) => { setLoading(true); setData(null); setSelected(event.target.value); setOffset(0); setError(""); setMessage(""); }}>{instruments.map((item) => <option key={item.id} value={item.id}>{item.symbol} · {item.exchange} · {item.name}</option>)}</select></label> : !loading ? <p>Ajoute un titre dans <Link className="text-signal underline" href="/portfolio">le portefeuille</Link> ou <Link className="text-signal underline" href="/international">les cotations internationales</Link>. Aucun calendrier fictif n’est ajouté.</p> : null}
    {loading ? <p role="status" className="my-4">Chargement…</p> : null}
    {data ? <>
      <section className="my-5 rounded-xl border border-white/10 p-5">
        <h2 className="text-xl text-white">Collecte automatique</h2>
        <p className="my-2 text-sm">Alpha Vantage · NYSE/Nasdaq en USD, unité 1 · horizon de trois mois. Quota partagé avec les cours, au maximum un quart du budget quotidien pour le calendrier (minimum une requête).</p>
        <p className="text-sm">{!data.collection.supported ? "Cette cotation reste à renseigner à partir d’une source autorisée." : !data.collection.configured ? "Clé ALPHA_VANTAGE_API_KEY absente côté serveur : collecte indisponible." : `Dernier état : ${{success: "collecte réussie", failed: "collecte échouée", pending: "en attente", running: "en cours"}[data.collection.status] ?? "non disponible"}.`}</p>
        {data.collection.started_at ? <p className="mt-2 text-sm">Tentative du {dateTime(data.collection.started_at)}{data.collection.error_code ? ` · ${data.collection.error_code}` : ""}{data.collection.retry_at ? ` · reprise au plus tôt ${dateTime(data.collection.retry_at)}` : ""}.</p> : null}
        <button disabled={busy || !data.collection.supported || !data.collection.configured} onClick={() => void collect()} className="mt-3 rounded border border-signal/40 px-3 py-2 text-signal disabled:opacity-40">Consulter le calendrier</button>
      </section>
      <details className="my-5 rounded-xl border border-white/10 p-5"><summary className="cursor-pointer text-white">Ajouter une date, une estimation ou un résultat sourcé</summary>
        <p className="my-3 text-sm">Pour toutes les cotations. Fournis une URL documentaire autorisée et sa date réelle de publication. Les saisies restent déclaratives ; aucune page n’est téléchargée à partir de ce formulaire. Un BPA ajusté ou une convention inconnue ne permet pas de comparaison automatique.</p>
        <form onSubmit={(event) => void save(event)}><fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
          <label>Observation<select aria-label="Observation" value={kind} onChange={(event) => setKind(event.target.value as Observation["kind"])} className={field}>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label>Périodicité<select aria-label="Périodicité" name="period_type" className={field}>{Object.entries(periods).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label>Fin de période fiscale<input required name="period" type="date" className={field} /></label>
          <label>Date prévue ou réelle des résultats<input required name="report" type="date" className={field} /></label>
          <label>URL du document source<input required name="source" type="url" className={field} /></label>
          <label>Publication de la source (heure locale)<input required name="published" type="datetime-local" className={field} /></label>
          {kind !== "schedule" ? <><label>BPA par action, négatif ou nul possible<input required name="eps" type="number" step="0.000001" className={field} /></label><label>Devise du BPA (pas déduite du cours)<input required name="currency" maxLength={3} minLength={3} className={field} /></label><label>Convention du BPA<select aria-label="Convention du BPA" name="basis" className={field}>{Object.entries(bases).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></> : null}
          <button disabled={busy} className="rounded border border-signal/40 p-2 text-signal disabled:opacity-40">Conserver l’observation</button>
        </fieldset></form>
      </details>
      <h2 id="calendar-history" className="mb-3 text-xl text-white">Historique sourcé</h2><p className="mb-4 text-sm">{data.notice} Une modification de calendrier crée une nouvelle observation ; les anciennes restent visibles.</p>
      {!data.items.length ? <p>Aucune observation disponible. Une réponse vide du fournisseur ne prouve pas l’absence de résultats à venir.</p> : null}
      {data.items.map((item) => <article key={item.id} className="mb-4 rounded-xl border border-white/10 p-4">
        <h3 className="text-lg text-white">{labels[item.kind]} · {item.report_date}</h3>
        <p className="mt-2 text-sm">Période terminée le {item.fiscal_period_end} · {periods[item.period_type]} · {item.provider === "manual" ? "Saisie déclarative" : "Calendrier fournisseur, rattachement par symbole"}.</p>
        {item.eps !== null ? <p className="mt-2">BPA : {item.eps} {item.currency} · {bases[item.basis]}</p> : null}
        {item.time_of_day ? <p className="mt-2 text-sm">Créneau indiqué par le fournisseur : {item.time_of_day} · fuseau horaire non fourni.</p> : null}
        <p className="mt-2 text-sm"><a href={item.source_url} target="_blank" rel="noreferrer" className="text-signal underline">Source</a> · {item.published_at ? `publiée le ${dateTime(item.published_at)}` : "date de publication non fournie par le fournisseur"} · première consultation {dateTime(item.observed_at)}.</p>
        {item.comparison ? <p className="mt-3 text-sm">{item.comparison.status === "comparable" ? <>Écart à l’estimation : {item.comparison.delta} {item.currency}{item.comparison.percent !== null ? ` (${item.comparison.percent} %)` : " · pourcentage indéfini : estimation nulle"}. <a href={item.comparison.estimate_source} target="_blank" rel="noreferrer" className="text-signal underline">Estimation source</a> du {dateTime(item.comparison.estimate_published_at!)}. {item.comparison.notice}</> : item.comparison.reason}</p> : null}
      </article>)}
      <Pagination page={offset / 10} pageSize={10} hasNext={data.next_offset !== null} busy={loading || busy} onChange={p => page(p * 10)} label="observations" targetId="calendar-history" />
    </> : null}
    <section className="mt-8 border-t border-white/10 pt-5 text-sm"><h2 className="text-xl text-white">Sources de veille proposées</h2>
      <p className="my-3">Liens de consultation ; ces sites ne sont pas des collecteurs connectés. Les flux et API nécessitant une autorisation restent à raccorder.</p>
      <div className="flex flex-wrap gap-4 text-signal underline">{[["Arkéa", "https://www.cm-arkea-sdm.com/app/news"], ["Investing — résultats", "https://www.investing.com/earnings-calendar"], ["Reuters", "https://www.reuters.com/"], ["Bloomberg", "https://www.bloomberg.com/europe"], ["Boursorama", "https://www.boursorama.com/bourse/"], ["Trading Economics", "https://fr.tradingeconomics.com/"], ["BCE", "https://www.ecb.europa.eu/home/html/index.en.html"]].map(([label, url]) => <a key={url} href={url} target="_blank" rel="noreferrer">{label}</a>)}</div>
    </section>
  </main>;
}
